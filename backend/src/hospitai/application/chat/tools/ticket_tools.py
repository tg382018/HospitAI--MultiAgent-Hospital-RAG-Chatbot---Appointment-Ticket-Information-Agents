"""Ticket / complaint chat tools: create, list, get, close."""

from __future__ import annotations

from typing import Any

import structlog
from state import ChatState

from hospitai.application import patient_identity as pid
from hospitai.application import tickets as ticket_svc
from hospitai.application.errors import DomainError
from hospitai.infrastructure import hospital_chat_bridge as hosp_bridge
from hospitai.infrastructure.db.models.enums import TicketPriority
from hospitai.infrastructure.db.session import get_session_factory

from .common import (
    bridge_identity_payload_fragment,
    bridge_identity_ready,
    bridge_map_tickets,
    bridge_patient_identity,
    get_tenant,
    get_user,
    guest_contact_ready,
)

log = structlog.get_logger(__name__)


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


async def create_ticket_tool(
    state: ChatState,
    subject: str,
    description: str,
    category: str = "general",
) -> dict[str, Any]:
    """Şikayet/talep: hastane köprüsü veya yerel kayıt."""
    async with get_session_factory()() as session:
        tenant = await get_tenant(session, state.tenant_slug)
        if not tenant:
            return {"success": False, "error": "Hastane bulunamadı."}

        desc = description.strip()

        if hosp_bridge.bridge_is_configured(tenant):
            user = await get_user(session, state.user_id, tenant.id)
            b = bridge_patient_identity(state)
            if user is not None:
                tc_u = (getattr(user, "national_id", None) or "").strip()
                if tc_u and pid.is_valid_turkish_national_id(tc_u):
                    b["national_id"] = tc_u
                ph_u = (getattr(user, "phone", None) or "").strip()
                ph_n = pid.normalize_tr_phone_digits(ph_u) if ph_u else None
                if ph_n:
                    b["phone"] = ph_n
                nm = (user.full_name or "").strip()
                if nm and len(nm) >= 3:
                    b["full_name"] = nm
            if not bridge_identity_ready(b):
                return {
                    "success": False,
                    "user_message_tr": (
                        "Talebi hastaneye iletmek için kayıtlı cep telefonunuz, ad-soyad ve "
                        "şikayet metni gerekir."
                    ),
                    "error": "bridge_identity_required",
                }
            br = await hosp_bridge.dispatch_hospital_bridge(
                tenant_slug=state.tenant_slug,
                tenant=tenant,
                operation="tickets/create",
                payload={
                    **bridge_identity_payload_fragment(b),
                    "subject": subject.strip()[:512],
                    "description": desc[:12000],
                    "phone": (state.guest_phone or "").strip() or b.get("phone") or None,
                    "email": (state.guest_email or "").strip() or None,
                    "conversation_id": (state.conversation_id or "").strip() or None,
                },
            )
            if br is not None:
                ref = str(br.get("reference") or "")
                um = (br.get("user_message_tr") or "").strip()
                ref_msg = f"Talep iletildi. Referans: {ref}" if ref else "Talep iletildi."
                return {
                    "success": bool(br.get("success")),
                    "reference": ref,
                    "message": um or ref_msg,
                }

        user = await get_user(session, state.user_id, tenant.id)
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
        elif guest_contact_ready(state):
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
    """Talep listesi: köprü (misafir + TC) veya yerel hesap."""
    async with get_session_factory()() as session:
        tenant = await get_tenant(session, state.tenant_slug)
        if not tenant:
            return {"success": False, "error": "Hastane bulunamadı."}

        user = await get_user(session, state.user_id, tenant.id)

        if user is None and hosp_bridge.bridge_is_configured(tenant):
            b = bridge_patient_identity(state)
            if not bridge_identity_ready(b):
                return {
                    "success": False,
                    "user_message_tr": (
                        "Taleplerinizi görmek için kayıtlı cep telefonunuz ve ad-soyadınızı yazın "
                        "(veya hesabınızla giriş yapın)."
                    ),
                }
            br = await hosp_bridge.dispatch_hospital_bridge(
                tenant_slug=state.tenant_slug,
                tenant=tenant,
                operation="tickets/query",
                payload={
                    **bridge_identity_payload_fragment(b),
                    "conversation_id": (state.conversation_id or "").strip() or None,
                },
            )
            if br is None:
                return {
                    "success": False,
                    "tickets": [],
                    "count": 0,
                    "user_message_tr": "Hastane köprüsü yapılandırılmadı veya yanıt alınamadı.",
                }
            if not br.get("success"):
                return {
                    "success": False,
                    "tickets": [],
                    "count": 0,
                    "user_message_tr": br.get("user_message_tr") or "Sorgu başarısız.",
                }
            rows = bridge_map_tickets(list(br.get("tickets") or []))
            um = (br.get("user_message_tr") or "").strip()
            return {
                "success": True,
                "tickets": rows,
                "count": len(rows),
                "user_message_tr": um or None,
            }

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
        tenant = await get_tenant(session, state.tenant_slug)
        if not tenant:
            return {
                "success": False,
                "ticket_outcome": "tenant_not_found",
                "error": "Hastane bulunamadı.",
                "user_message_tr": "Hastane bulunamadı.",
            }

        user = await get_user(session, state.user_id, tenant.id)
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
    """Resolve TKT-… from ``user_message`` then delegate."""
    from tools.ticket_reference import extract_ticket_reference

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


async def create_ticket_from_message_for_graph(state: ChatState, message: str) -> dict[str, Any]:
    subject, description = _parse_complaint_for_ticket(message)
    if not (state.guest_full_name or "").strip():
        stated = pid.extract_stated_full_name(message, "")
        if stated.strip():
            import dataclasses

            state = dataclasses.replace(state, guest_full_name=stated.strip())
    if not (state.guest_phone or "").strip():
        phone = pid.extract_phone_from_text(message)
        if phone:
            import dataclasses

            state = dataclasses.replace(state, guest_phone=phone)
    return await create_ticket_tool(
        state,
        subject=subject,
        description=description,
        category="general",
    )


async def close_ticket_tool(state: ChatState, reference: str) -> dict[str, Any]:
    """Close (resolve) a support ticket by reference."""
    ref = reference.strip()
    if not ref:
        return {
            "success": False,
            "user_message_tr": "Kapatmak istediğiniz talebin TKT referansını belirtin.",
        }
    async with get_session_factory()() as session:
        tenant = await get_tenant(session, state.tenant_slug)
        if not tenant:
            return {"success": False, "user_message_tr": "Hastane bulunamadı."}
        user = await get_user(session, state.user_id, tenant.id)
        try:
            ticket = await ticket_svc.close_ticket(
                session,
                tenant_id=tenant.id,
                reference=ref,
                actor=user,
            )
            await session.commit()
            return {
                "success": True,
                "user_message_tr": (
                    f"Talebiniz ({ticket.reference}) kapatıldı. "
                    "Farklı bir sorununuz olursa yeni talep oluşturabilirsiniz."
                ),
            }
        except DomainError as e:
            return {"success": False, "user_message_tr": e.message}
