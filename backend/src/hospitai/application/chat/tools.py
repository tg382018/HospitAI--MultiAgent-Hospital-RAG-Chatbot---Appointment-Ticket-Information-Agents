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
from hospitai.application.chat.slot_tool_result import wrap_slot_tool_error, wrap_slot_tool_success
from hospitai.application.errors import DomainError
from hospitai.infrastructure.db.models.enums import TicketPriority
from hospitai.infrastructure.db.session import get_session_factory

log = structlog.get_logger(__name__)


def _fmt_dt(value: object) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value or "")


def _guest_contact_ready(state: ChatState) -> bool:
    return bool((state.guest_full_name or "").strip() and (state.guest_phone or "").strip())


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
            return wrap_slot_tool_error(
                outcome="tenant_not_found",
                error="Hastane bulunamadı.",
            )

        base = (tenant.external_hospital_base_url or "").strip()
        ext_meta: dict[str, Any] | None = None
        if base:
            from hospitai.infrastructure import hospital_connector as ext

            try:
                slots, ext_meta = await ext.list_external_slots_merged(
                    base_url=base,
                    api_key=(tenant.external_hospital_api_key or "").strip() or None,
                    for_date=day,
                    doctor_name_substr=doctor_name or None,
                    department_substr=department_name or None,
                )
            except httpx.HTTPError as exc:
                log.warning("external_slots_http_error", error=str(exc))
                msg = (
                    "Dış randevu sistemine şu an ulaşılamıyor. "
                    "Lütfen daha sonra tekrar deneyin veya randevu hattını arayın."
                )
                return wrap_slot_tool_error(
                    outcome="upstream_transport",
                    error=msg,
                    user_message_tr=msg,
                )
        else:
            slots = await appt_svc.list_available_slots_for_chat(
                session,
                tenant_id=tenant.id,
                day=day,
                department_name=department_name or None,
                doctor_name=doctor_name or None,
            )

        serialized_slots = [
            {
                "doctor": s["doctor_name"],
                "department": s["department_name"],
                "start": _fmt_dt(s["start_time"]),
                "end": _fmt_dt(s["end_time"]),
            }
            for s in slots
        ]
        return wrap_slot_tool_success(
            day=day,
            source="external" if base else "internal",
            serialized_slots=serialized_slots,
            ext_meta=ext_meta,
            filter_department=department_name or "",
            filter_doctor=doctor_name or "",
        )


async def list_available_slots_for_graph(state: ChatState) -> dict[str, Any]:
    """Graph entrypoint: parse ``user_message`` hints then delegate to slot listing."""
    from hospitai_agent.slot_params import extract_slot_query_params

    p = extract_slot_query_params(state.user_message)
    return await list_available_slots_tool(
        state,
        department_name=p.get("department_name") or "",
        doctor_name=p.get("doctor_name") or "",
        target_date=p.get("target_date") or "",
    )


async def list_appointments_tool(state: ChatState) -> dict[str, Any]:
    """List user's upcoming appointments."""
    async with get_session_factory()() as session:
        tenant = await _get_tenant(session, state.tenant_slug)
        if not tenant:
            return {"success": False, "error": "Hastane bulunamadı."}

        user = await _get_user(session, state.user_id, tenant.id)
        if not user:
            return {
                "success": True,
                "appointments": [],
                "count": 0,
                "user_message_tr": (
                    "Oturum açmadan hesabınıza bağlı randevu listesi gösterilemez. "
                    "Müsait saatleri sorabilir veya randevu için bilgi hattını arayabilirsiniz."
                ),
            }

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
                    "doctor": a.doctor.full_name if a.doctor else "N/A",
                    "department": a.department.name if a.department else "N/A",
                    "start": a.starts_at.isoformat() if a.starts_at else "",
                    "end": a.ends_at.isoformat() if a.ends_at else "",
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
        desc = description.strip()
        if user:
            ticket = await ticket_svc.create_ticket(
                session,
                tenant_id=tenant.id,
                actor=user,
                subject=subject,
                description=desc,
                category=category,
                priority=TicketPriority.MEDIUM,
            )
        elif _guest_contact_ready(state):
            suffix = (
                "\n\n--- Misafir iletişim (kayıtlı hesap yok) ---\n"
                f"Ad Soyad: {(state.guest_full_name or '').strip()}\n"
                f"Telefon: {(state.guest_phone or '').strip()}\n"
                f"E-posta: {(state.guest_email or '').strip() or '—'}\n"
            )
            ticket = await ticket_svc.create_ticket(
                session,
                tenant_id=tenant.id,
                actor=None,
                subject=subject,
                description=(desc + suffix)[:12000],
                category=category,
                priority=TicketPriority.MEDIUM,
            )
        else:
            return {
                "success": False,
                "user_message_tr": (
                    "Talebinizi kaydetmek için ad soyad ve telefon numaranızı paylaşın "
                    "(tercihen e-posta). Bilgileri iletişim alanına yazıp tekrar deneyebilir "
                    "veya mesajınızda belirtebilirsiniz."
                ),
                "error": "guest_contact_required",
            }

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
            return {
                "success": True,
                "tickets": [],
                "count": 0,
                "user_message_tr": (
                    "Oturum açmadan talep listesi gösterilemez. Yeni talep için ad ve telefon "
                    "verin veya oluşturduğunuz TKT- referansı ile durum sorgulayın."
                ),
            }

        tickets = await ticket_svc.list_tickets(
            session,
            tenant_id=tenant.id,
            actor=user,
            status=None,
            limit=50,
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


async def get_ticket_status_by_reference_tool(
    state: ChatState,
    *,
    reference: str,
) -> dict[str, Any]:
    """Single ticket by reference; enforced owner/staff via domain service."""
    ref = reference.strip()
    if not ref:
        return {
            "success": False,
            "ticket_outcome": "empty_reference",
            "error": "empty_reference",
            "user_message_tr": "Geçerli bir referans kodu gerekli.",
        }

    async with get_session_factory()() as session:
        tenant = await _get_tenant(session, state.tenant_slug)
        if not tenant:
            return {
                "success": False,
                "ticket_outcome": "tenant_not_found",
                "error": "Hastane bulunamadı.",
                "user_message_tr": "Hastane bulunamadı.",
            }

        user = await _get_user(session, state.user_id, tenant.id)
        actor = user if user is not None else None

        try:
            ticket = await ticket_svc.get_ticket_by_reference(
                session,
                tenant_id=tenant.id,
                reference=ref,
                actor=actor,
            )
        except DomainError as e:
            if e.code == "ticket_not_found":
                user_tr = (
                    f"{ref} referanslı bir talep bu hastanede bulunamadı. "
                    "Numarayı kontrol edin veya talepleriniz listesinden doğrulayın."
                )
            elif e.code == "forbidden":
                user_tr = (
                    "Bu referansa ait talebi yalnızca kaydı oluşturan kullanıcı görüntüleyebilir. "
                    "Oturumunuzun doğru hesaba ait olduğundan emin olun."
                )
            else:
                user_tr = e.message
            return {
                "success": False,
                "ticket_outcome": e.code,
                "error": e.message,
                "user_message_tr": user_tr,
                "reference": ref,
            }

        st = ticket.status.value if hasattr(ticket.status, "value") else str(ticket.status)
        pr = ticket.priority.value if hasattr(ticket.priority, "value") else str(ticket.priority)
        created = ticket.created_at.isoformat() if ticket.created_at else "—"
        user_tr = (
            f"Talep {ticket.reference}: durum {st}, öncelik {pr}. "
            f"Konu: {ticket.subject}. Oluşturulma: {created}."
        )
        return {
            "success": True,
            "ticket_outcome": "found",
            "user_message_tr": user_tr,
            "reference": ticket.reference,
            "status": st,
            "subject": ticket.subject,
            "category": ticket.category or "",
            "priority": pr,
            "created_at": created,
        }


async def get_ticket_by_reference_for_graph(state: ChatState) -> dict[str, Any]:
    """Resolve TKT-… from ``user_message`` then delegate (complaint graph node)."""
    from hospitai_agent.ticket_reference import extract_ticket_reference

    ref = extract_ticket_reference(state.user_message)
    if not ref:
        return {
            "success": False,
            "ticket_outcome": "no_reference_in_message",
            "error": "no_reference_in_message",
            "user_message_tr": (
                "Mesajınızda TKT- ile başlayan geçerli bir referans kodu bulunamadı. "
                "Durumunu öğrenmek istediğiniz talebin referansını "
                "(ör. TKT- ile başlayan kod) yazın."
            ),
        }
    return await get_ticket_status_by_reference_tool(state, reference=ref)


def _parse_complaint_for_ticket(message: str) -> tuple[str, str]:
    """Derive ticket subject + description from free-form user text."""
    text = message.strip()
    lowered = text.lower()
    for ph in (
        "şikayet oluşturmak istiyorum",
        "talep oluşturmak istiyorum",
        "yeni talep oluşturmak istiyorum",
        "şikayet kaydı açmak istiyorum",
        "başvuru yapmak istiyorum",
    ):
        if ph in lowered:
            i = lowered.index(ph)
            text = (text[:i] + text[i + len(ph) :]).strip(" :.,;\n\t-")
            lowered = text.lower()
            break
    if ":" in text:
        left, right = text.split(":", 1)
        subject = left.strip()[:200] or "Hasta talebi"
        description = right.strip() or text
        return subject, description[:8000]
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if len(lines) >= 2:
        return lines[0][:200], "\n".join(lines[1:])[:8000]
    if len(text) > 160:
        cut = text[:140].rfind(" ")
        head = text[: cut if cut > 40 else 120]
        return (head + "…", text[:8000])
    return "Hasta talebi", text[:8000]


async def create_ticket_from_message_for_graph(state: ChatState, message: str) -> dict[str, Any]:
    subject, description = _parse_complaint_for_ticket(message)
    return await create_ticket_tool(
        state,
        subject=subject,
        description=description,
        category="general",
    )


async def retrieve_knowledge_tool(state: ChatState, query: str) -> dict[str, Any]:
    """Retrieve relevant context from tenant's knowledge base."""
    try:
        chunks = await rag_svc.retrieve_context(
            state.tenant_slug,
            query=query,
            n_results=10,
        )

        sources = list(
            {
                c.get("metadata", {}).get("title", "")
                for c in chunks
                if c.get("metadata", {}).get("title")
            }
        )

        texts = [c.get("content") or "" for c in chunks]
        merged = "\n\n".join(t for t in texts if t.strip())

        return {
            "success": True,
            "context": merged,
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
    "get_ticket_by_reference": get_ticket_by_reference_for_graph,
    "retrieve_knowledge": retrieve_knowledge_tool,
    "hospital_info": hospital_info_tool,
}


def make_workflow_tools() -> ChatWorkflowTools:
    """Bindings passed to `hospitai_agent.graph.configure_workflow_tools`."""
    return ChatWorkflowTools(
        list_available_slots=list_available_slots_for_graph,
        list_user_appointments=list_appointments_tool,
        list_tickets=list_tickets_tool,
        get_ticket_by_reference=get_ticket_by_reference_for_graph,
        retrieve_knowledge=retrieve_knowledge_tool,
        create_ticket_from_message=create_ticket_from_message_for_graph,
    )
