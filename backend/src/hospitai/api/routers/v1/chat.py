"""Chat endpoint — powered by the LangGraph workflow."""

from __future__ import annotations

import json
import re
import uuid
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Header, Request
from fastapi.responses import StreamingResponse
from hospitai_agent.state import ChatState
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from hospitai.api.deps import OptionalUser, SettingsDep
from hospitai.api.errors import AppError
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
from hospitai.infrastructure.settings import Settings

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


async def _resolve_tenant_for_chat(
    session: AsyncSession,
    *,
    user: User | None,
    x_tenant_slug: str | None,
    settings: Settings,
) -> tuple[Tenant, uuid.UUID, str]:
    if user is not None:
        stmt = select(Tenant).where(Tenant.id == user.tenant_id)
        row = await session.execute(stmt)
        tenant = row.scalar_one_or_none()
        if tenant is None:
            raise AppError("tenant_missing", "Hastane kaydı bulunamadı.", status_code=503)
        slug = (tenant.slug or "").strip() or settings.public_chat_default_tenant_slug
        return tenant, user.tenant_id, slug

    slug = (x_tenant_slug or "").strip() or settings.public_chat_default_tenant_slug
    stmt = select(Tenant).where(Tenant.slug == slug)
    row = await session.execute(stmt)
    tenant = row.scalar_one_or_none()
    if tenant is None:
        raise AppError(
            "tenant_not_found",
            f"Hastane bulunamadı (slug: {slug}).",
            status_code=404,
        )
    return tenant, tenant.id, slug


def _merge_guest_profile(conv: Conversation, body: ChatRequest) -> dict[str, str]:
    meta = dict(conv.extra) if conv.extra else {}
    guest = dict(meta.get("guest") or {})
    if body.guest_full_name and body.guest_full_name.strip():
        guest["full_name"] = body.guest_full_name.strip()[:255]
    if body.guest_phone and body.guest_phone.strip():
        guest["phone"] = body.guest_phone.strip()[:64]
    if body.guest_email and body.guest_email.strip():
        guest["email"] = body.guest_email.strip()[:320]
    if body.guest_national_id and body.guest_national_id.strip():
        g = re.sub(r"\D", "", body.guest_national_id.strip())
        if len(g) == 11:
            guest["national_id"] = g
    meta["guest"] = guest
    conv.extra = meta
    return guest


def _guest_from_conv(conv: Conversation) -> dict[str, str]:
    raw = (conv.extra or {}).get("guest") if conv.extra else None
    return dict(raw) if isinstance(raw, dict) else {}


def _guest_dict_to_state_fields(guest: dict[str, Any]) -> tuple[str, str, str, str]:
    nid = str(guest.get("national_id") or "")
    if nid and len(nid) != 11:
        nid = re.sub(r"\D", "", nid)[:11]
    return (
        str(guest.get("full_name") or ""),
        str(guest.get("phone") or ""),
        str(guest.get("email") or ""),
        nid,
    )


def _patient_verification_user_id(conv: Conversation) -> str:
    raw = (conv.extra or {}).get("patient_verification") if conv.extra else None
    if not isinstance(raw, dict):
        return ""
    return str(raw.get("patient_user_id") or "").strip()


async def _save_assistant_and_maybe_audit(
    session: AsyncSession,
    *,
    conv: Conversation,
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    result: dict[str, Any],
    client: str | None,
    user_agent: str | None,
) -> None:
    await save_message(
        session,
        conversation_id=conv.id,
        tenant_id=tenant_id,
        role="assistant",
        content=result["response"],
    )
    if result.get("safety_flag"):
        await write_audit_log(
            session,
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
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
async def chat(
    request: Request,
    body: ChatRequest,
    user: OptionalUser,
    settings: SettingsDep,
    x_tenant_slug: Annotated[str | None, Header(alias="X-Tenant-Slug")] = None,
) -> ChatResponse:
    """Send a message to the AI assistant.

    JWT isteğe bağlıdır: token yoksa ``X-Tenant-Slug`` veya
    ``PUBLIC_CHAT_DEFAULT_TENANT_SLUG`` ile hastane seçilir; sohbet misafir olarak devam eder.
    """
    async with get_session_factory()() as session:
        _, tenant_id, tenant_slug = await _resolve_tenant_for_chat(
            session, user=user, x_tenant_slug=x_tenant_slug, settings=settings
        )
        _, llm_overrides, max_hist = await _tenant_slug_and_agent_overrides(
            session, tenant_id=tenant_id
        )

        conv = await get_or_create_conversation(
            session,
            tenant_id=tenant_id,
            user_id=user.id if user else None,
            conversation_id=body.conversation_id,
        )
        if user is None:
            _merge_guest_profile(conv, body)
        guest_src = _guest_from_conv(conv)
        gn, gp, ge, gid = _guest_dict_to_state_fields(guest_src)
        vu = _patient_verification_user_id(conv) if user is None else ""

        cs = ChatState(
            user_message=body.message,
            tenant_slug=tenant_slug,
            user_role=(
                (user.role.value if hasattr(user.role, "value") else str(user.role))
                if user
                else "guest"
            ),
            user_id=str(user.id) if user else "",
            llm_overrides=dict(llm_overrides),
            guest_full_name=gn,
            guest_phone=gp,
            guest_email=ge,
            guest_national_id=gid,
            conversation_id=str(conv.id),
            verified_patient_user_id=vu,
        )

        cs = await load_memory(cs, session, conv.id, max_messages=max_hist)

        await save_message(
            session,
            conversation_id=conv.id,
            tenant_id=tenant_id,
            role="user",
            content=body.message,
        )
        await session.commit()

    result = await run_chat(
        user_message=body.message,
        tenant_slug=tenant_slug,
        user_id=str(user.id) if user else "",
        user_role=(
            (user.role.value if hasattr(user.role, "value") else str(user.role))
            if user
            else "guest"
        ),
        history=cs.history,
        llm_overrides=llm_overrides or None,
        guest_full_name=gn,
        guest_phone=gp,
        guest_email=ge,
        guest_national_id=gid,
        conversation_id=str(conv.id),
        verified_patient_user_id=vu,
    )

    client = request.client.host if request.client else None
    ua = request.headers.get("user-agent")

    async with get_session_factory()() as session:
        await _save_assistant_and_maybe_audit(
            session,
            conv=conv,
            tenant_id=tenant_id,
            actor_user_id=user.id if user else None,
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
async def chat_stream(
    request: Request,
    body: ChatRequest,
    user: OptionalUser,
    settings: SettingsDep,
    x_tenant_slug: Annotated[str | None, Header(alias="X-Tenant-Slug")] = None,
) -> StreamingResponse:
    """SSE: ``meta`` (conversation id), ``token`` chunks, ``final`` (assistant payload)."""
    try:
        async with get_session_factory()() as session:
            _, tenant_id, tenant_slug = await _resolve_tenant_for_chat(
                session, user=user, x_tenant_slug=x_tenant_slug, settings=settings
            )
            _, llm_overrides, max_hist = await _tenant_slug_and_agent_overrides(
                session, tenant_id=tenant_id
            )

            conv = await get_or_create_conversation(
                session,
                tenant_id=tenant_id,
                user_id=user.id if user else None,
                conversation_id=body.conversation_id,
            )
            if user is None:
                _merge_guest_profile(conv, body)
            guest_src = _guest_from_conv(conv)
            gn, gp, ge, gid = _guest_dict_to_state_fields(guest_src)
            vu = _patient_verification_user_id(conv) if user is None else ""

            cs = ChatState(
                user_message=body.message,
                tenant_slug=tenant_slug,
                user_role=(
                    (user.role.value if hasattr(user.role, "value") else str(user.role))
                    if user
                    else "guest"
                ),
                user_id=str(user.id) if user else "",
                llm_overrides=dict(llm_overrides),
                guest_full_name=gn,
                guest_phone=gp,
                guest_email=ge,
                guest_national_id=gid,
                conversation_id=str(conv.id),
                verified_patient_user_id=vu,
            )
            cs = await load_memory(cs, session, conv.id, max_messages=max_hist)
            await save_message(
                session,
                conversation_id=conv.id,
                tenant_id=tenant_id,
                role="user",
                content=body.message,
            )
            await session.commit()
    except AppError:
        raise
    except (ConnectionRefusedError, TimeoutError) as exc:
        # asyncpg / TCP: port kapalı veya Postgres ayakta değil (SQLAlchemyError dışında kalabilir).
        log.exception("chat_stream_db_unreachable", error=str(exc))
        raise AppError(
            "database_unavailable",
            "Veritabanına bağlanılamıyor. `docker compose -f infra/docker-compose.yml ps` ile "
            "Postgres'in çalıştığını doğrulayın; `backend/.env` içindeki DATABASE_URL host/portu "
            "compose eşlemesiyle aynı olsun (ör. 5432↔5432 veya 15432↔5432). Ardından "
            "`alembic upgrade head`.",
            status_code=503,
        ) from exc
    except SQLAlchemyError as exc:
        log.exception("chat_stream_db_error", error=str(exc))
        raise AppError(
            "database_unavailable",
            "Veritabanına bağlanılamıyor. Postgres'in çalıştığını ve "
            "`alembic upgrade head` ile migrasyonların uygulandığını kontrol edin.",
            status_code=503,
        ) from exc
    except Exception:
        log.exception("chat_stream_prepare_failed")
        raise AppError(
            "chat_prepare_failed",
            "Sohbet oturumu başlatılamadı. Sunucu günlüklerine bakın.",
            status_code=503,
        ) from None

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
                user_id=str(user.id) if user else "",
                user_role=(
                    (user.role.value if hasattr(user.role, "value") else str(user.role))
                    if user
                    else "guest"
                ),
                history=cs.history,
                llm_overrides=llm_overrides or None,
                guest_full_name=gn,
                guest_phone=gp,
                guest_email=ge,
                guest_national_id=gid,
                conversation_id=str(conv.id),
                verified_patient_user_id=vu,
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
                tenant_id=tenant_id,
                actor_user_id=user.id if user else None,
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
