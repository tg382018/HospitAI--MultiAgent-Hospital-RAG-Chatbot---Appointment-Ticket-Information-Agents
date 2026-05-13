"""Chat endpoint — powered by the LangGraph workflow."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Request
from hospitai_agent.state import ChatState

from hospitai.api.deps import CurrentUser
from hospitai.api.schemas.chat import ChatRequest, ChatResponse
from hospitai.application.audit import write_audit_log
from hospitai.application.chat import run_chat
from hospitai.application.chat.memory import (
    get_or_create_conversation,
    load_memory,
    save_message,
)
from hospitai.infrastructure.db.session import get_session_factory

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
async def chat(request: Request, body: ChatRequest, user: CurrentUser) -> ChatResponse:
    """Send a message to the AI assistant.

    The workflow runs: safety → intent classification → routing →
    tools / RAG → response generation → output safety.
    """
    from sqlalchemy import select

    from hospitai.infrastructure.db.models.tenant import Tenant

    async with get_session_factory()() as session:
        # Resolve tenant slug (async-safe — no lazy loading)
        stmt = select(Tenant.slug).where(Tenant.id == user.tenant_id)
        result_row = await session.execute(stmt)
        tenant_slug = result_row.scalar_one_or_none() or ""

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
        )

        # Load conversation memory
        cs = await load_memory(cs, session, conv.id)

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
    )

    # Save assistant response + optional security audit
    client = request.client.host if request.client else None
    ua = request.headers.get("user-agent")

    async with get_session_factory()() as session:
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
