"""Agent tools callable by the LangGraph chat workflow.

Each tool wraps existing application-layer services, adding
tenant-scoped context and formatting results for conversational output.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx
import structlog
from hospitai_agent.state import ChatState
from sqlalchemy.orm import selectinload
from hospitai_agent.tools.contracts import ChatWorkflowTools

from hospitai.application import appointments as appt_svc
from hospitai.application import patient_identity as pid
from hospitai.application import rag as rag_svc
from hospitai.application import tickets as ticket_svc
from hospitai.application.chat.slot_tool_result import wrap_slot_tool_error, wrap_slot_tool_success
from hospitai.application.errors import DomainError
from hospitai.infrastructure import hospital_chat_bridge as hosp_bridge
from hospitai.infrastructure.db.models.enums import TicketPriority
from hospitai.infrastructure.db.session import get_session_factory

log = structlog.get_logger(__name__)


def _fmt_dt(value: object) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value or "")


def _guest_contact_ready(state: ChatState) -> bool:
    return bool((state.guest_full_name or "").strip() and (state.guest_phone or "").strip())


def _effective_patient_user_id(state: ChatState) -> str:
    u = (state.user_id or "").strip()
    if u:
        return u
    return (state.verified_patient_user_id or "").strip()


def _bridge_patient_identity(state: ChatState) -> dict[str, str | None]:
    """Misafir hastane köprüsü için TC ve/veya cep + ad-soyad (mesaj veya iletişim formu)."""
    name = (pid.extract_stated_full_name(state.user_message, state.guest_full_name) or "").strip()
    name_ok = name if len(name) >= 3 else None
    tc_raw = pid.extract_tc_from_text(state.user_message) or pid.normalize_tc(
        state.guest_national_id or ""
    )
    tc = tc_raw if tc_raw and pid.is_valid_turkish_national_id(tc_raw) else None
    phone = pid.extract_phone_from_text(state.user_message) or pid.normalize_tr_phone_digits(
        state.guest_phone or ""
    )
    return {"national_id": tc, "phone": phone, "full_name": name_ok}


def _bridge_identity_ready(b: dict[str, str | None]) -> bool:
    return bool(b.get("full_name")) and bool(b.get("national_id") or b.get("phone"))


def _bridge_identity_payload_fragment(b: dict[str, str | None]) -> dict[str, Any]:
    out: dict[str, Any] = {"full_name": b["full_name"]}
    if b.get("national_id"):
        out["national_id"] = b["national_id"]
    if b.get("phone"):
        out["phone"] = b["phone"]
    return out


def _bridge_map_appointments(raw: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        out.append(
            {
                "id": str(row.get("id") or row.get("appointment_id") or ""),
                "doctor": str(row.get("doctor") or row.get("doctor_name") or "N/A"),
                "department": str(row.get("department") or row.get("department_name") or "N/A"),
                "start": str(
                    row.get("start") or row.get("starts_at") or row.get("start_time") or ""
                ),
                "end": str(row.get("end") or row.get("ends_at") or row.get("end_time") or ""),
                "status": str(row.get("status") or ""),
            }
        )
    return out


def _bridge_map_tickets(raw: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        out.append(
            {
                "reference": str(row.get("reference") or row.get("ticket_reference") or ""),
                "subject": str(row.get("subject") or ""),
                "status": str(row.get("status") or ""),
                "created_at": str(row.get("created_at") or row.get("created") or ""),
            }
        )
    return out


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
    """Graph entrypoint: use LLM-extracted params (via llm_overrides) or fall back to
    keyword parsing of user_message for backward compatibility."""
    sp = (state.llm_overrides or {}).get("slot_params")
    if isinstance(sp, dict):
        return await list_available_slots_tool(
            state,
            department_name=str(sp.get("department_name") or ""),
            doctor_name=str(sp.get("doctor_name") or ""),
            target_date=str(sp.get("target_date") or ""),
        )

    from hospitai_agent.tools.slot_params import extract_slot_query_params

    p = extract_slot_query_params(state.user_message)
    return await list_available_slots_tool(
        state,
        department_name=p.get("department_name") or "",
        doctor_name=p.get("doctor_name") or "",
        target_date=p.get("target_date") or "",
    )


async def list_doctors_tool(
    state: ChatState,
    department_name: str = "",
    doctor_name: str = "",
) -> dict[str, Any]:
    """Aktif doktorları DB'den listele — bölüm veya isim filtresiyle."""
    from sqlalchemy import func as sa_func

    from hospitai.infrastructure.db.models.clinical import Department, Doctor

    async with get_session_factory()() as session:
        tenant = await _get_tenant(session, state.tenant_slug)
        if not tenant:
            return {"success": False, "user_message_tr": "Hastane bulunamadı."}

        from sqlalchemy import select as sa_select

        stmt = (
            sa_select(Doctor, Department.name.label("dept_name"))
            .outerjoin(Department, Doctor.department_id == Department.id)
            .where(Doctor.tenant_id == tenant.id, Doctor.is_active.is_(True))
        )

        import re as _re

        dn = (doctor_name or "").strip()
        if dn:
            dn_bare = _re.sub(r"^[Dd][Rr]\.?\s*", "", dn).strip()
            from hospitai.application.appointments import _ascii_normalize
            dn_norm = _ascii_normalize(dn_bare).lower()
            col_norm = sa_func.lower(
                sa_func.translate(
                    sa_func.regexp_replace(Doctor.full_name, r"^Dr\.?\s*", "", "i"),
                    "şçğıöüŞÇĞİÖÜ", "scgiouSCGIOU",
                )
            )
            stmt = stmt.where(col_norm.ilike(f"%{dn_norm}%"))

        dep_q = (department_name or "").strip()
        if dep_q:
            dep_norm = dep_q.lower()
            dept_col = sa_func.lower(
                sa_func.translate(Department.name, "şçğıöüŞÇĞİÖÜ", "scgiouSCGIOU")
            )
            stmt = stmt.where(dept_col.ilike(f"%{dep_norm}%"))

        stmt = stmt.order_by(Department.name, Doctor.full_name)
        rows = list((await session.execute(stmt)).all())

        if not rows:
            msg = "Bu kriterlere uyan aktif doktor bulunamadı."
            if dep_q:
                msg = f"'{dep_q}' bölümünde aktif doktor bulunamadı."
            return {"success": False, "user_message_tr": msg}

        # Group by department
        by_dept: dict[str, list[str]] = {}
        for row in rows:
            dept = row.dept_name or "Genel"
            by_dept.setdefault(dept, []).append(row.Doctor.full_name)

        lines = []
        for dept, docs in by_dept.items():
            lines.append(f"**{dept}**: {', '.join(docs)}")

        return {
            "success": True,
            "user_message_tr": "\n".join(lines),
            "doctors": [
                {"name": r.Doctor.full_name, "department": r.dept_name or "Genel"}
                for r in rows
            ],
        }


async def list_appointments_tool(state: ChatState) -> dict[str, Any]:
    """Randevu listesi: köprü (HTTP/Rabbit) veya yerel DB (JWT / yerel doğrulama)."""
    async with get_session_factory()() as session:
        tenant = await _get_tenant(session, state.tenant_slug)
        if not tenant:
            return {"success": False, "error": "Hastane bulunamadı."}

        if hosp_bridge.bridge_is_configured(tenant):
            b = _bridge_patient_identity(state)
            if not _bridge_identity_ready(b):
                return {
                    "success": False,
                    "user_message_tr": (
                        "Randevu bilgilerinizi hastane sisteminden almak için kayıtlı "
                        "cep telefonunuzu ve ad-soyadınızı yazın "
                        "(iletişim formuyla da girebilirsiniz)."
                    ),
                }
            br = await hosp_bridge.dispatch_hospital_bridge(
                tenant_slug=state.tenant_slug,
                tenant=tenant,
                operation="appointments/query",
                payload={
                    **_bridge_identity_payload_fragment(b),
                    "conversation_id": (state.conversation_id or "").strip() or None,
                },
            )
            if br is not None:
                if br.get("bridge_queued"):
                    return {
                        "success": True,
                        "appointments": [],
                        "count": 0,
                        "user_message_tr": br.get("user_message_tr", ""),
                    }
                if not br.get("success"):
                    return {
                        "success": False,
                        "appointments": [],
                        "count": 0,
                        "user_message_tr": br.get("user_message_tr")
                        or "Randevu sorgusu reddedildi.",
                    }
                appts = _bridge_map_appointments(list(br.get("appointments") or []))
                um = (br.get("user_message_tr") or "").strip()
                if not um and appts:
                    um = f"{len(appts)} randevu kaydı listelendi."
                return {
                    "success": True,
                    "appointments": appts,
                    "count": len(appts),
                    "user_message_tr": um or "Kayıt bulunamadı.",
                }

        eff = _effective_patient_user_id(state)
        # Try phone-based lookup for guest users
        if not eff:
            phone = pid.extract_phone_from_text(state.user_message) or pid.normalize_tr_phone_digits(
                state.guest_phone or ""
            )
            if phone:
                candidate = await pid.find_patient_by_phone(
                    session, tenant_id=tenant.id, phone_digits=phone
                )
                if candidate:
                    eff = str(candidate.id)

        user = await _get_user(session, eff, tenant.id) if eff else None

        # For guests without a user account, look up appointments by guest_contact
        if not user:
            phone = pid.extract_phone_from_text(state.user_message) or pid.normalize_tr_phone_digits(
                state.guest_phone or ""
            )
            if phone:
                from sqlalchemy import select as sa_select

                from hospitai.infrastructure.db.models.appointment import Appointment

                stmt = (
                    sa_select(Appointment)
                    .where(
                        Appointment.tenant_id == tenant.id,
                        Appointment.guest_contact == phone,
                        Appointment.status != appt_svc.AppointmentStatus.CANCELLED,
                    )
                    .options(selectinload(Appointment.doctor), selectinload(Appointment.department))
                    .order_by(Appointment.starts_at.desc())
                    .limit(20)
                )
                rows = list((await session.execute(stmt)).scalars().all())
                if rows:
                    return {
                        "success": True,
                        "appointments": _bridge_map_appointments(
                            [
                                {
                                    "id": str(a.id),
                                    "doctor_name": a.doctor.full_name if a.doctor else "N/A",
                                    "department_name": a.department.name if a.department else "N/A",
                                    "start_time": a.starts_at.isoformat() if a.starts_at else "",
                                    "end_time": a.ends_at.isoformat() if a.ends_at else "",
                                    "status": a.status.value if hasattr(a.status, "value") else str(a.status),
                                }
                                for a in rows
                            ]
                        ),
                        "count": len(rows),
                    }
            return {
                "success": True,
                "appointments": [],
                "count": 0,
                "user_message_tr": (
                    "Randevularınızı görmek için kayıtlı cep telefonunuzu yazın."
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


async def verify_patient_identity_tool(state: ChatState) -> dict[str, Any]:
    """Telefon veya TC + ad-soyad: köprü açıksa format + metadata; değilse yerel DB doğrulama."""
    if (state.user_id or "").strip():
        return {
            "success": True,
            "skipped": True,
            "user_message_tr": (
                "Oturum açmış durumdasınız; randevularınız hesabınıza göre listelenir. "
                "Misafir doğrulaması yalnızca giriş yapmadan yazarken gereklidir."
            ),
        }

    stated = pid.extract_stated_full_name(state.user_message, state.guest_full_name)
    if not stated.strip():
        return {
            "success": False,
            "user_message_tr": (
                "Kayıtlı ad-soyadınızla aynı olacak şekilde adınızı ve soyadınızı yazın "
                "(veya iletişim formundaki ad soyad alanını doldurun)."
            ),
        }

    phone = pid.extract_phone_from_text(state.user_message) or pid.normalize_tr_phone_digits(
        state.guest_phone or ""
    )
    tc_raw = pid.extract_tc_from_text(state.user_message) or pid.normalize_tc(
        state.guest_national_id or ""
    )
    tc = tc_raw if tc_raw and pid.is_valid_turkish_national_id(tc_raw) else None

    if not phone and not tc:
        return {
            "success": False,
            "user_message_tr": (
                "Randevu ve talepler için kayıtlı cep telefon numaranızı "
                "(ör. 05xx xxx xx xx) ve ad-soyadınızı yazın. "
                "Kimlik numaranızı yalnızca hastanenin resmi güvenli kanallarında paylaşın."
            ),
        }

    conv_key = (state.conversation_id or "").strip()
    if not conv_key:
        return {
            "success": False,
            "user_message_tr": (
                "Önce bir mesaj göndererek sohbet oturumunu başlatın, ardından tekrar deneyin."
            ),
        }

    try:
        conv_uuid = uuid.UUID(conv_key)
    except (ValueError, TypeError):
        return {"success": False, "user_message_tr": "Geçersiz sohbet oturumu."}

    from sqlalchemy import select

    from hospitai.infrastructure.db.models.conversation import Conversation

    patient_user_id_str = ""

    async with get_session_factory()() as session:
        tenant = await _get_tenant(session, state.tenant_slug)
        if not tenant:
            return {"success": False, "user_message_tr": "Hastane bulunamadı."}

        if hosp_bridge.bridge_is_configured(tenant):
            crow = await session.execute(
                select(Conversation).where(
                    Conversation.id == conv_uuid,
                    Conversation.tenant_id == tenant.id,
                )
            )
            conv = crow.scalar_one_or_none()
            if conv is None:
                return {"success": False, "user_message_tr": "Sohbet oturumu bulunamadı."}
            meta = dict(conv.extra) if conv.extra else {}
            bridge_id: dict[str, str] = {"full_name": stated.strip()[:255]}
            if tc:
                bridge_id["national_id"] = tc
            if phone:
                bridge_id["phone"] = phone
            meta["patient_bridge_identity"] = bridge_id
            conv.extra = meta
            await session.commit()
            return {
                "success": True,
                "user_message_tr": (
                    "İletişim bilgileriniz alındı. Randevu veya talep işlemleri hastane sistemine "
                    "iletilmeye hazır."
                ),
            }

        patient = None
        matched_by_phone = False
        if phone:
            patient = await pid.find_patient_by_phone(
                session, tenant_id=tenant.id, phone_digits=phone
            )
            if patient is not None:
                matched_by_phone = True
        if patient is None and tc:
            patient = await pid.find_patient_by_national_id(
                session,
                tenant_id=tenant.id,
                national_id=tc,
            )

        if patient is None:
            return {
                "success": False,
                "user_message_tr": (
                    "Bu bilgilerle bu hastanede kayıtlı hasta bulunamadı. "
                    "Kayıtlı cep telefonunuzu ve ad-soyadınızı kontrol edin veya "
                    "kayıt için hastane müracaatını kullanın."
                ),
            }

        if not pid.names_match(stated=stated, stored=patient.full_name):
            return {
                "success": False,
                "user_message_tr": (
                    "Ad-soyad bilgisi sistemdeki kayıtla eşleşmedi. Lütfen kayıtlı ad-soyadınızla "
                    "aynı şekilde yazın."
                ),
            }

        crow = await session.execute(
            select(Conversation).where(
                Conversation.id == conv_uuid,
                Conversation.tenant_id == tenant.id,
            )
        )
        conv = crow.scalar_one_or_none()
        if conv is None:
            return {"success": False, "user_message_tr": "Sohbet oturumu bulunamadı."}

        meta = dict(conv.extra) if conv.extra else {}
        pv: dict[str, str] = {"patient_user_id": str(patient.id)}
        if matched_by_phone and phone:
            pv["phone_last4"] = phone[-4:]
        if tc:
            pv["national_id_last4"] = tc[-4:]
        meta["patient_verification"] = pv
        conv.extra = meta
        patient_user_id_str = str(patient.id)
        await session.commit()

    return {
        "success": True,
        "patient_user_id": patient_user_id_str or None,
        "user_message_tr": (
            "Doğrulama tamam. Randevularınızı veya yeni randevu talebinizi söyleyebilirsiniz."
        ),
    }


async def book_appointment_tool(
    state: ChatState,
    *,
    doctor_name: str,
    starts_at_iso: str,
    department_name: str = "",
) -> dict[str, Any]:
    """Randevu oluştur: hastane köprüsü (HTTP/Rabbit) veya yerel takvim."""
    dn = (doctor_name or "").strip()
    if len(dn) < 2:
        return {
            "success": False,
            "user_message_tr": "Hangi doktor için randevu istediğinizi (doktor adı) yazın.",
        }

    try:
        starts_at = datetime.fromisoformat(starts_at_iso.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return {
            "success": False,
            "user_message_tr": (
                "Başlangıç saatini anlayamadım. Örnek: 2026-12-20T14:30:00+00:00 veya "
                "2026-12-20 14:30 biçiminde yazın."
            ),
        }
    if starts_at.tzinfo is None:
        starts_at = starts_at.replace(tzinfo=UTC)
    ends_at = starts_at + timedelta(minutes=30)

    async with get_session_factory()() as session:
        tenant = await _get_tenant(session, state.tenant_slug)
        if not tenant:
            return {"success": False, "user_message_tr": "Hastane bulunamadı."}

        if hosp_bridge.bridge_is_configured(tenant):
            b = _bridge_patient_identity(state)
            if not _bridge_identity_ready(b):
                return {
                    "success": False,
                    "user_message_tr": (
                        "Randevu talebini hastaneye iletmek için kayıtlı cep telefonunuz ve "
                        "ad-soyad gerekir (iletişim formu veya mesaj)."
                    ),
                }
            br = await hosp_bridge.dispatch_hospital_bridge(
                tenant_slug=state.tenant_slug,
                tenant=tenant,
                operation="appointments/book",
                payload={
                    **_bridge_identity_payload_fragment(b),
                    "starts_at": starts_at.isoformat(),
                    "ends_at": ends_at.isoformat(),
                    "doctor_name": dn,
                    "department_name": (department_name or "").strip() or None,
                    "conversation_id": (state.conversation_id or "").strip() or None,
                },
            )
            if br is not None:
                ref = str(br.get("reference") or "")
                um = (br.get("user_message_tr") or "").strip() or (
                    "Randevu isteğiniz hastane sistemine iletildi." if br.get("success") else ""
                )
                return {
                    "success": bool(br.get("success")),
                    "appointment_id": ref,
                    "user_message_tr": um or "Randevu işlemi tamamlanamadı.",
                }

        # Extract guest identity from message or state fields (set by agent tool executor)
        guest_phone = pid.extract_phone_from_text(state.user_message) or pid.normalize_tr_phone_digits(
            state.guest_phone or ""
        )
        guest_name = (
            pid.extract_stated_full_name(state.user_message, state.guest_full_name) or ""
        ).strip()

        # Try to find a registered patient for linked booking (optional, nice to have)
        eff = _effective_patient_user_id(state)
        if not eff and guest_phone:
            candidate = await pid.find_patient_by_phone(
                session, tenant_id=tenant.id, phone_digits=guest_phone
            )
            if candidate is not None:
                eff = str(candidate.id)

        patient = await _get_user(session, eff, tenant.id) if eff else None

        doc, dcode = await appt_svc.find_active_doctor_by_name(
            session, tenant_id=tenant.id, name_substr=dn
        )
        if dcode == "not_found":
            return {
                "success": False,
                "user_message_tr": f"'{dn}' ile eşleşen aktif doktor bulunamadı.",
            }
        if dcode == "ambiguous":
            return {
                "success": False,
                "user_message_tr": (
                    f"'{dn}' için birden fazla doktor eşleşti. Lütfen doktor adını daha net yazın."
                ),
            }
        if doc is None:
            return {"success": False, "user_message_tr": "Doktor seçilemedi."}

        dept_id: uuid.UUID | None = None
        dep_q = (department_name or "").strip()
        if dep_q:
            from sqlalchemy import select

            from hospitai.infrastructure.db.models.clinical import Department

            dstmt = (
                select(Department)
                .where(
                    Department.tenant_id == tenant.id,
                    Department.is_active.is_(True),
                    Department.name.ilike(f"%{dep_q}%"),
                )
                .limit(2)
            )
            drows = list((await session.execute(dstmt)).scalars().all())
            if len(drows) == 1:
                dept_id = drows[0].id

        notes = "Chat üzerinden oluşturuldu"
        if not patient and guest_name:
            notes = f"Chat üzerinden oluşturuldu — Misafir: {guest_name}, Tel: {guest_phone or '—'}"

        try:
            appt = await appt_svc.create_appointment(
                session,
                tenant_id=tenant.id,
                actor=patient,
                doctor_id=doc.id,
                starts_at=starts_at,
                ends_at=ends_at,
                department_id=dept_id,
                notes=notes,
                patient_user_id=None,
                guest_display_name=guest_name or None,
                guest_contact=guest_phone or None,
            )
        except DomainError as e:
            return {
                "success": False,
                "user_message_tr": e.message or "Randevu oluşturulamadı.",
            }

        await session.commit()
        st = appt.starts_at.isoformat() if appt.starts_at else ""
        display = doc.full_name
        return {
            "success": True,
            "appointment_id": str(appt.id),
            "user_message_tr": (
                f"Randevunuz oluşturuldu. Doktor: {display}. Başlangıç: {st}. "
                "İptal veya değişiklik için randevu hattını arayabilirsiniz."
            ),
        }


async def book_appointment_from_graph(state: ChatState) -> dict[str, Any]:
    """Graph entrypoint: use LLM-extracted params (via llm_overrides) or fall back to
    regex parsing of user_message for backward compatibility."""
    bp = (state.llm_overrides or {}).get("book_params")
    if isinstance(bp, dict) and bp.get("starts_at"):
        return await book_appointment_tool(
            state,
            doctor_name=str(bp.get("doctor_name") or ""),
            starts_at_iso=str(bp.get("starts_at") or ""),
            department_name=str(bp.get("department_name") or ""),
        )

    from hospitai_agent.tools.slot_params import extract_slot_query_params

    msg = state.user_message
    p = extract_slot_query_params(msg)
    doctor = (p.get("doctor_name") or "").strip()
    dept = (p.get("department_name") or "").strip()

    tm = re.search(
        r"\b(20\d{2}-\d{2}-\d{2})[T\s](\d{1,2}:\d{2})(?::(\d{2}))?\b",
        msg,
    )
    starts_iso = ""
    if tm:
        day, hm = tm.group(1), tm.group(2)
        parts = hm.split(":")
        h, mi = int(parts[0]), int(parts[1])
        sec = int(tm.group(3)) if tm.group(3) else 0
        starts_iso = f"{day}T{h:02d}:{mi:02d}:{sec:02d}+00:00"

    if not starts_iso:
        return {
            "success": False,
            "user_message_tr": (
                "Randevu için tarih ve saat yazın (ör. 2026-12-20 14:30) ve doktor adını belirtin."
            ),
        }

    if not doctor:
        mdoc = re.search(
            r"(?:\bdr\.?\s*|\bdoktoru?\s+)([A-Za-zÇĞİÖŞÜçğıöşüa-zı\s\.]{2,60})",
            msg,
            re.IGNORECASE,
        )
        if mdoc:
            doctor = re.sub(r"\s+", " ", mdoc.group(1).strip()).strip(" .")

    return await book_appointment_tool(
        state,
        doctor_name=doctor,
        starts_at_iso=starts_iso,
        department_name=dept,
    )


async def cancel_appointment_from_graph(state: ChatState) -> dict[str, Any]:
    """Randevu iptali — köprü varsa oradan, yoksa yerel DB'den."""
    async with get_session_factory()() as session:
        tenant = await _get_tenant(session, state.tenant_slug)
        if not tenant:
            return {"success": False, "user_message_tr": "Hastane bulunamadı."}

        # Bridge path
        if hosp_bridge.bridge_is_configured(tenant):
            b = _bridge_patient_identity(state)
            if not _bridge_identity_ready(b):
                return {
                    "success": False,
                    "user_message_tr": (
                        "İptal için kayıtlı cep telefonunuz ve ad-soyadınızı yazın."
                    ),
                }
            aid = hosp_bridge.extract_uuid_from_text(state.user_message)
            br = await hosp_bridge.dispatch_hospital_bridge(
                tenant_slug=state.tenant_slug,
                tenant=tenant,
                operation="appointments/cancel",
                payload={
                    **_bridge_identity_payload_fragment(b),
                    "appointment_id": aid,
                    "user_message": state.user_message[:4000],
                    "conversation_id": (state.conversation_id or "").strip() or None,
                },
            )
            if br is not None:
                return {
                    "success": bool(br.get("success")),
                    "user_message_tr": (br.get("user_message_tr") or "").strip() or "İptal iletildi.",
                }

        # Local DB path — find appointment by guest phone or registered user
        from sqlalchemy import select as sa_select

        from hospitai.infrastructure.db.models.appointment import Appointment
        from hospitai.infrastructure.db.models.enums import AppointmentStatus

        guest_phone = pid.extract_phone_from_text(state.user_message) or pid.normalize_tr_phone_digits(
            state.guest_phone or ""
        )

        # Try explicit UUID reference first
        appt_id_str = hosp_bridge.extract_uuid_from_text(state.user_message)

        eff = _effective_patient_user_id(state)
        if not eff and guest_phone:
            candidate = await pid.find_patient_by_phone(session, tenant_id=tenant.id, phone_digits=guest_phone)
            if candidate:
                eff = str(candidate.id)

        appt = None
        if appt_id_str:
            try:
                import uuid as _uuid
                stmt = sa_select(Appointment).where(
                    Appointment.tenant_id == tenant.id,
                    Appointment.id == _uuid.UUID(appt_id_str),
                )
                appt = (await session.execute(stmt)).scalar_one_or_none()
            except (ValueError, TypeError):
                pass

        if appt is None and guest_phone:
            # Find upcoming appointment by guest phone
            from datetime import UTC, datetime
            stmt = (
                sa_select(Appointment)
                .where(
                    Appointment.tenant_id == tenant.id,
                    Appointment.guest_contact == guest_phone,
                    Appointment.status != AppointmentStatus.CANCELLED,
                    Appointment.starts_at >= datetime.now(UTC),
                )
                .order_by(Appointment.starts_at.asc())
                .limit(1)
            )
            appt = (await session.execute(stmt)).scalar_one_or_none()

        if appt is None and eff:
            from datetime import UTC, datetime
            stmt = (
                sa_select(Appointment)
                .where(
                    Appointment.tenant_id == tenant.id,
                    Appointment.patient_user_id == _uuid.UUID(eff),
                    Appointment.status != AppointmentStatus.CANCELLED,
                    Appointment.starts_at >= datetime.now(UTC),
                )
                .order_by(Appointment.starts_at.asc())
                .limit(1)
            )
            appt = (await session.execute(stmt)).scalar_one_or_none()

        if appt is None:
            return {
                "success": False,
                "user_message_tr": (
                    "İptal edilecek aktif randevu bulunamadı. "
                    "Cep telefonunuzu yazarak tekrar deneyin."
                ),
            }

        appt.status = AppointmentStatus.CANCELLED
        await session.commit()
        st = appt.starts_at.strftime("%d %B %Y %H:%M") if appt.starts_at else ""
        return {
            "success": True,
            "user_message_tr": f"Randevunuz iptal edildi. ({st})",
        }


async def create_ticket_tool(
    state: ChatState,
    subject: str,
    description: str,
    category: str = "general",
) -> dict[str, Any]:
    """Şikayet/talep: hastane köprüsü veya yerel kayıt."""
    async with get_session_factory()() as session:
        tenant = await _get_tenant(session, state.tenant_slug)
        if not tenant:
            return {"success": False, "error": "Hastane bulunamadı."}

        desc = description.strip()

        if hosp_bridge.bridge_is_configured(tenant):
            user = await _get_user(session, state.user_id, tenant.id)
            b = _bridge_patient_identity(state)
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
            if not _bridge_identity_ready(b):
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
                    **_bridge_identity_payload_fragment(b),
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

        user = await _get_user(session, state.user_id, tenant.id)
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
    """Talep listesi: köprü (misafir + TC) veya yerel hesap."""
    async with get_session_factory()() as session:
        tenant = await _get_tenant(session, state.tenant_slug)
        if not tenant:
            return {"success": False, "error": "Hastane bulunamadı."}

        user = await _get_user(session, state.user_id, tenant.id)

        if user is None and hosp_bridge.bridge_is_configured(tenant):
            b = _bridge_patient_identity(state)
            if not _bridge_identity_ready(b):
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
                    **_bridge_identity_payload_fragment(b),
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
            rows = _bridge_map_tickets(list(br.get("tickets") or []))
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
    from hospitai_agent.tools.ticket_reference import extract_ticket_reference

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
    # Extract identity from message into state if not already set
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
        tenant = await _get_tenant(session, state.tenant_slug)
        if not tenant:
            return {"success": False, "user_message_tr": "Hastane bulunamadı."}
        user = await _get_user(session, state.user_id, tenant.id)
        try:
            from hospitai.application import tickets as ticket_svc
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
        list_doctors=list_doctors_tool,
        list_available_slots=list_available_slots_for_graph,
        list_user_appointments=list_appointments_tool,
        list_tickets=list_tickets_tool,
        get_ticket_by_reference=get_ticket_by_reference_for_graph,
        retrieve_knowledge=retrieve_knowledge_tool,
        create_ticket_from_message=create_ticket_from_message_for_graph,
        close_ticket=close_ticket_tool,
        verify_patient_identity=verify_patient_identity_tool,
        book_appointment=book_appointment_from_graph,
        cancel_appointment=cancel_appointment_from_graph,
    )
