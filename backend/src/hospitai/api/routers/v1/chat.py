"""Chat endpoint — powered by the LangGraph workflow."""

from __future__ import annotations

import json
import uuid
from typing import Any

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from hospitai_agent.state import ChatState
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from hospitai.api.deps import CurrentUser
from hospitai.api.schemas.chat import ChatRequest, ChatResponse
from hospitai.application.audit import write_audit_log
from hospitai.application.chat import iter_chat_sse, run_chat
from hospitai.application.chat.memory import (
    get_or_create_conversation,
    load_memory,
    save_message,
)
from hospitai.application.tenant_agent_llm import (
    effective_max_conversation_history,
    graph_llm_overrides_from_tenant_settings,
)
from hospitai.infrastructure.db.models.conversation import Conversation
from hospitai.infrastructure.db.models.tenant import Tenant
from hospitai.infrastructure.db.models.user import User
from hospitai.infrastructure.db.session import get_session_factory

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


async def _tenant_slug_and_agent_overrides(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
) -> tuple[str, dict[str, Any], int]:
    stmt = select(Tenant).where(Tenant.id == tenant_id)
    row = await session.execute(stmt)
    tenant = row.scalar_one_or_none()
    slug = (tenant.slug or "") if tenant else ""
    settings = tenant.settings if tenant and isinstance(tenant.settings, dict) else None
    llm_ov = graph_llm_overrides_from_tenant_settings(settings)
    max_h = effective_max_conversation_history(settings)
    return slug, llm_ov, max_h


async def _save_assistant_and_maybe_audit(
    session: AsyncSession,
    *,
    conv: Conversation,
    user: User,
    result: dict[str, Any],
    client: str | None,
    user_agent: str | None,
) -> None:
    await save_message(
        session,
        conversation_id=conv.id,
        tenant_id=user.tenant_id,
        role="assistant",
        content=result["response"],
    )
    if result.get("safety_flag"):
        await write_audit_log(
            session,
            tenant_id=user.tenant_id,
            actor_user_id=user.id,
            action="chat.safety_block",
            resource_type="conversation",
            resource_id=conv.id,
            payload={
                "intent": result.get("intent"),
                "reason": result.get("safety_reason", ""),
                "escalated": bool(result.get("escalated")),
            },
            ip_address=client,
            user_agent=user_agent,
        )


@router.post("", response_model=ChatResponse)
async def chat(request: Request, body: ChatRequest, user: CurrentUser) -> ChatResponse:
    """Send a message to the AI assistant.

    The workflow runs: safety → intent classification → routing →
    tools / RAG → response generation → output safety.
    """
    async with get_session_factory()() as session:
        tenant_slug, llm_overrides, max_hist = await _tenant_slug_and_agent_overrides(
            session, tenant_id=user.tenant_id
        )

        conv = await get_or_create_conversation(
            session,
            tenant_id=user.tenant_id,
            user_id=user.id,
            conversation_id=body.conversation_id,
        )

        cs = ChatState(
            user_message=body.message,
            tenant_slug=tenant_slug,
            user_role=user.role.value if hasattr(user.role, "value") else str(user.role),
            user_id=str(user.id),
            llm_overrides=dict(llm_overrides),
        )

        # Load conversation memory
        cs = await load_memory(cs, session, conv.id, max_messages=max_hist)

        # Save user message
        await save_message(
            session,
            conversation_id=conv.id,
            tenant_id=user.tenant_id,
            role="user",
            content=body.message,
        )
        await session.commit()

    # Run the LangGraph workflow
    result = await run_chat(
        user_message=body.message,
        tenant_slug=tenant_slug,
        user_id=str(user.id),
        user_role=user.role.value if hasattr(user.role, "value") else str(user.role),
        history=cs.history,
        llm_overrides=llm_overrides or None,
    )

    # Save assistant response + optional security audit
    client = request.client.host if request.client else None
    ua = request.headers.get("user-agent")

    async with get_session_factory()() as session:
        await _save_assistant_and_maybe_audit(
            session,
            conv=conv,
            user=user,
            result=result,
            client=client,
            user_agent=ua,
        )
        await session.commit()

    return ChatResponse(
        conversation_id=conv.id,
        message=result["response"],
        intent=result["intent"],
        sources=result.get("sources", []),
        rag_used=bool(result.get("rag_used", False)),
        escalated=bool(result.get("escalated", False)),
        safety_flag=result.get("safety_flag", False),
        safety_reason=result.get("safety_reason", ""),
    )


@router.post("/stream")
async def chat_stream(request: Request, body: ChatRequest, user: CurrentUser) -> StreamingResponse:
    """SSE: ``meta`` (conversation id), ``token`` chunks, ``final`` (assistant payload)."""
    async with get_session_factory()() as session:
        tenant_slug, llm_overrides, max_hist = await _tenant_slug_and_agent_overrides(
            session, tenant_id=user.tenant_id
        )

        conv = await get_or_create_conversation(
            session,
            tenant_id=user.tenant_id,
            user_id=user.id,
            conversation_id=body.conversation_id,
        )

        cs = ChatState(
            user_message=body.message,
            tenant_slug=tenant_slug,
            user_role=user.role.value if hasattr(user.role, "value") else str(user.role),
            user_id=str(user.id),
            llm_overrides=dict(llm_overrides),
        )
        cs = await load_memory(cs, session, conv.id, max_messages=max_hist)
        await save_message(
            session,
            conversation_id=conv.id,
            tenant_id=user.tenant_id,
            role="user",
            content=body.message,
        )
        await session.commit()

    client = request.client.host if request.client else None
    ua = request.headers.get("user-agent")
    boxed: dict[str, Any] = {}

    async def event_gen():
        meta = json.dumps({"conversation_id": str(conv.id)}, ensure_ascii=False)
        yield f"event: meta\ndata: {meta}\n\n"
        try:
            async for raw in iter_chat_sse(
                user_message=body.message,
                tenant_slug=tenant_slug,
                user_id=str(user.id),
                user_role=user.role.value if hasattr(user.role, "value") else str(user.role),
                history=cs.history,
                llm_overrides=llm_overrides or None,
            ):
                yield raw
                if raw.startswith("event: final"):
                    for line in raw.splitlines():
                        if line.startswith("data: "):
                            boxed["result"] = json.loads(line[6:])
        except Exception as exc:
            log.exception("chat_stream_error", error=str(exc))
            yield f"event: error\ndata: {json.dumps({'message': str(exc)}, ensure_ascii=False)}\n\n"
            return

        result = boxed.get("result")
        if not isinstance(result, dict):
            log.error("chat_stream_missing_final")
            return
        async with get_session_factory()() as session:
            await _save_assistant_and_maybe_audit(
                session,
                conv=conv,
                user=user,
                result=result,
                client=client,
                user_agent=ua,
            )
            await session.commit()

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
