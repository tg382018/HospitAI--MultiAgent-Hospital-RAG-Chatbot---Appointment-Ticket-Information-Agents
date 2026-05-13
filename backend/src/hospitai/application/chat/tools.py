"""Agent tools callable by the LangGraph chat workflow.

Each tool wraps existing application-layer services, adding
tenant-scoped context and formatting results for conversational output.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

import httpx
import structlog
from hospitai_agent.state import ChatState
from hospitai_agent.workflow_tools import ChatWorkflowTools

from hospitai.application import appointments as appt_svc
from hospitai.application import rag as rag_svc
from hospitai.application import tickets as ticket_svc
from hospitai.infrastructure.db.session import get_session_factory

log = structlog.get_logger(__name__)


def _fmt_dt(value: object) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value or "")


# ---------------------------------------------------------------------------
# Appointment tools
# ---------------------------------------------------------------------------


async def list_available_slots_tool(
    state: ChatState,
    department_name: str = "",
    doctor_name: str = "",
    target_date: str = "",
) -> dict[str, Any]:
    """List available appointment slots. Returns slot list or error."""
    async with get_session_factory()() as session:
        try:
            day = date.fromisoformat(target_date) if target_date else date.today()
        except ValueError:
            day = date.today()

        # Find tenant
        from sqlalchemy import select

        from hospitai.infrastructure.db.models.tenant import Tenant

        stmt = select(Tenant).where(Tenant.slug == state.tenant_slug)
        result = await session.execute(stmt)
        tenant = result.scalar_one_or_none()
        if not tenant:
            return {"success": False, "error": "Hastane bulunamadı."}

        base = (tenant.external_hospital_base_url or "").strip()
        if base:
            from hospitai.infrastructure import hospital_connector as ext

            try:
                slots = await ext.list_external_slots_merged(
                    base_url=base,
                    api_key=(tenant.external_hospital_api_key or "").strip() or None,
                    for_date=day,
                    doctor_name_substr=doctor_name or None,
                    department_substr=department_name or None,
                )
            except httpx.HTTPError as exc:
                log.warning("external_slots_http_error", error=str(exc))
                return {
                    "success": False,
                    "error": (
                        "Dış randevu sistemine şu an ulaşılamıyor. "
                        "Lütfen daha sonra tekrar deneyin."
                    ),
                }
        else:
            slots = await appt_svc.list_available_slots_for_chat(
                session,
                tenant_id=tenant.id,
                day=day,
                department_name=department_name or None,
                doctor_name=doctor_name or None,
            )

        return {
            "success": True,
            "date": day.isoformat(),
            "slots": [
                {
                    "doctor": s["doctor_name"],
                    "department": s["department_name"],
                    "start": _fmt_dt(s["start_time"]),
                    "end": _fmt_dt(s["end_time"]),
                }
                for s in slots
            ],
            "count": len(slots),
            "source": "external" if base else "internal",
        }


async def list_appointments_tool(state: ChatState) -> dict[str, Any]:
    """List user's upcoming appointments."""
    async with get_session_factory()() as session:
        tenant = await _get_tenant(session, state.tenant_slug)
        if not tenant:
            return {"success": False, "error": "Hastane bulunamadı."}

        user = await _get_user(session, state.user_id, tenant.id)
        if not user:
            return {"success": False, "error": "Kullanıcı bulunamadı."}

        appointments = await appt_svc.list_appointments_for_actor(
            session,
            user=user,
            tenant_id=tenant.id,
        )

        return {
            "success": True,
            "appointments": [
                {
                    "id": str(a.id),
                    "doctor": getattr(getattr(a, "doctor", None), "name", "N/A"),
                    "department": getattr(getattr(a, "department", None), "name", "N/A"),
                    "start": a.start_time.isoformat() if a.start_time else "",
                    "status": a.status.value if hasattr(a.status, "value") else str(a.status),
                }
                for a in appointments
            ],
            "count": len(appointments),
        }


# ---------------------------------------------------------------------------
# Ticket / complaint tools
# ---------------------------------------------------------------------------


async def create_ticket_tool(
    state: ChatState,
    subject: str,
    description: str,
    category: str = "general",
) -> dict[str, Any]:
    """Create a complaint ticket."""
    async with get_session_factory()() as session:
        tenant = await _get_tenant(session, state.tenant_slug)
        if not tenant:
            return {"success": False, "error": "Hastane bulunamadı."}

        user = await _get_user(session, state.user_id, tenant.id)
        if not user:
            return {"success": False, "error": "Kullanıcı bulunamadı."}

        ticket = await ticket_svc.create_ticket(
            session,
            tenant_id=tenant.id,
            user_id=user.id,
            subject=subject,
            description=description,
            category=category,
        )
        await session.commit()

        return {
            "success": True,
            "reference": ticket.reference,
            "message": f"Talebiniz oluşturuldu. Referans numaranız: {ticket.reference}",
        }


async def list_tickets_tool(state: ChatState) -> dict[str, Any]:
    """List user's complaint tickets."""
    async with get_session_factory()() as session:
        tenant = await _get_tenant(session, state.tenant_slug)
        if not tenant:
            return {"success": False, "error": "Hastane bulunamadı."}

        user = await _get_user(session, state.user_id, tenant.id)
        if not user:
            return {"success": False, "error": "Kullanıcı bulunamadı."}

        tickets = await ticket_svc.list_tickets(
            session,
            tenant_id=tenant.id,
            user_id=user.id,
        )

        return {
            "success": True,
            "tickets": [
                {
                    "reference": t.reference,
                    "subject": t.subject,
                    "status": t.status.value if hasattr(t.status, "value") else str(t.status),
                    "created_at": t.created_at.isoformat() if t.created_at else "",
                }
                for t in tickets
            ],
            "count": len(tickets),
        }


# ---------------------------------------------------------------------------
# RAG / knowledge retrieval
# ---------------------------------------------------------------------------


async def retrieve_knowledge_tool(state: ChatState, query: str) -> dict[str, Any]:
    """Retrieve relevant context from tenant's knowledge base."""
    try:
        chunks = await rag_svc.retrieve_context(
            state.tenant_slug,
            query=query,
            n_results=5,
        )

        sources = list(
            {
                c.get("metadata", {}).get("title", "")
                for c in chunks
                if c.get("metadata", {}).get("title")
            }
        )

        return {
            "success": True,
            "context": "\n\n".join(c.get("content", "") for c in chunks),
            "sources": sources,
        }
    except Exception as exc:
        log.warning("rag_retrieval_error", error=str(exc))
        return {"success": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# Hospital info (static + RAG-backed)
# ---------------------------------------------------------------------------


async def hospital_info_tool(state: ChatState, query: str) -> dict[str, Any]:
    """Retrieve hospital-specific information from the knowledge base."""
    result = await retrieve_knowledge_tool(state, query)
    if result.get("success") and not result.get("context"):
        result["fallback"] = (
            "Bu konuda bilgi bulunamadı. Lütfen hastane bilgi hattını arayın "
            "veya web sitemizi ziyaret edin."
        )
    return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_tenant(session, tenant_slug: str):
    from sqlalchemy import select

    from hospitai.infrastructure.db.models.tenant import Tenant

    stmt = select(Tenant).where(Tenant.slug == tenant_slug)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def _get_user(session, user_id: str, tenant_id: uuid.UUID):
    from sqlalchemy import select

    from hospitai.infrastructure.db.models.user import User

    try:
        uid = uuid.UUID(user_id)
    except (ValueError, TypeError):
        return None

    stmt = select(User).where(User.id == uid, User.tenant_id == tenant_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# Tool registry for the graph
# ---------------------------------------------------------------------------

TOOL_REGISTRY: dict[str, Any] = {
    "list_available_slots": list_available_slots_tool,
    "list_appointments": list_appointments_tool,
    "create_ticket": create_ticket_tool,
    "list_tickets": list_tickets_tool,
    "retrieve_knowledge": retrieve_knowledge_tool,
    "hospital_info": hospital_info_tool,
}


def make_workflow_tools() -> ChatWorkflowTools:
    """Bindings passed to `hospitai_agent.graph.configure_workflow_tools`."""
    return ChatWorkflowTools(
        list_available_slots=list_available_slots_tool,
        list_tickets=list_tickets_tool,
        retrieve_knowledge=retrieve_knowledge_tool,
    )
