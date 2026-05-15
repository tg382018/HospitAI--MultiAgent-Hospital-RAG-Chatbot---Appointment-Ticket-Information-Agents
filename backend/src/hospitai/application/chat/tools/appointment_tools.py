"""Appointment-related chat tools: list slots, list doctors, book, cancel."""

from __future__ import annotations

import re
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any, cast

import httpx
import structlog
from sqlalchemy.orm import selectinload
from state import ChatState

from hospitai.application import appointments as appt_svc
from hospitai.application import patient_identity as pid
from hospitai.application.chat.slot_tool_result import (
    SlotToolOutcome,
    wrap_slot_tool_error,
    wrap_slot_tool_success,
)
from hospitai.application.errors import DomainError
from hospitai.infrastructure import hospital_chat_bridge as hosp_bridge
from hospitai.infrastructure.db.session import get_session_factory

from .common import (
    _TZ_TURKEY,
    bridge_identity_payload_fragment,
    bridge_identity_ready,
    bridge_map_appointments,
    bridge_patient_identity,
    effective_patient_user_id,
    fmt_dt,
    get_tenant,
    get_user,
    today_in_turkey,
)

log = structlog.get_logger(__name__)


def _parse_slot_list_day(raw: str) -> tuple[date | None, str | None, str | None]:
    """Parse target date for slot listing.

    Returns ``(day, None, None)`` on success, or
    ``(None, slot_outcome, user_message_tr)`` on failure.
    """
    s = (raw or "").strip()
    if not s:
        return (
            None,
            "date_required",
            "Hangi gün için müsait randevu görmek istediğinizi belirtir misiniz? "
            "Örneğin: bugün, yarın veya 2026-05-20 gibi bir tarih yazabilirsiniz.",
        )

    tl = s.lower()
    td = today_in_turkey()

    if tl in ("bugün", "bugun", "today"):
        day = td
    elif tl in ("yarın", "yarin", "tomorrow"):
        day = td + timedelta(days=1)
    else:
        try:
            day = date.fromisoformat(s)
        except ValueError:
            return (
                None,
                "invalid_date",
                "Tarihi anlayamadım. Lütfen YYYY-AA-GG biçiminde (ör. 2026-05-20), "
                "'bugün' veya 'yarın' yazın.",
            )

    if day < td:
        return (
            None,
            "past_date",
            "Geçmiş bir tarih için randevu alınamaz. Lütfen bugün veya ileri bir tarih söyleyin.",
        )

    return (day, None, None)


async def list_available_slots_tool(
    state: ChatState,
    department_name: str = "",
    doctor_name: str = "",
    target_date: str = "",
) -> dict[str, Any]:
    """List available appointment slots. Returns slot list or error."""
    day, err_outcome, err_tr = _parse_slot_list_day(target_date)
    if err_outcome is not None:
        return wrap_slot_tool_error(
            outcome=cast(SlotToolOutcome, err_outcome),
            error=err_outcome,
            user_message_tr=err_tr,
        )

    async with get_session_factory()() as session:
        tenant = await get_tenant(session, state.tenant_slug)
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
                "start": fmt_dt(s["start_time"]),
                "end": fmt_dt(s["end_time"]),
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

    from tools.slot_params import extract_slot_query_params

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
    from sqlalchemy import select as sa_select

    from hospitai.infrastructure.db.models.clinical import Department, Doctor

    async with get_session_factory()() as session:
        tenant = await get_tenant(session, state.tenant_slug)
        if not tenant:
            return {"success": False, "user_message_tr": "Hastane bulunamadı."}

        stmt = (
            sa_select(Doctor, Department.name.label("dept_name"))
            .outerjoin(Department, Doctor.department_id == Department.id)
            .where(Doctor.tenant_id == tenant.id, Doctor.is_active.is_(True))
        )

        dn = (doctor_name or "").strip()
        if dn:
            dn_bare = re.sub(r"^[Dd][Rr]\.?\s*", "", dn).strip()
            from hospitai.application.appointments import _ascii_normalize

            dn_norm = _ascii_normalize(dn_bare).lower()
            col_norm = sa_func.lower(
                sa_func.translate(
                    sa_func.regexp_replace(Doctor.full_name, r"^Dr\.?\s*", "", "i"),
                    "şçğıöüŞÇĞİÖÜ",
                    "scgiouSCGIOU",
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
                {"name": r.Doctor.full_name, "department": r.dept_name or "Genel"} for r in rows
            ],
        }


async def list_appointments_tool(state: ChatState) -> dict[str, Any]:
    """Randevu listesi: köprü (HTTP/Rabbit) veya yerel DB (JWT / yerel doğrulama)."""
    async with get_session_factory()() as session:
        tenant = await get_tenant(session, state.tenant_slug)
        if not tenant:
            return {"success": False, "error": "Hastane bulunamadı."}

        if hosp_bridge.bridge_is_configured(tenant):
            b = bridge_patient_identity(state)
            if not bridge_identity_ready(b):
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
                    **bridge_identity_payload_fragment(b),
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
                appts = bridge_map_appointments(list(br.get("appointments") or []))
                um = (br.get("user_message_tr") or "").strip()
                if not um and appts:
                    um = f"{len(appts)} randevu kaydı listelendi."
                return {
                    "success": True,
                    "appointments": appts,
                    "count": len(appts),
                    "user_message_tr": um or "Kayıt bulunamadı.",
                }

        eff = effective_patient_user_id(state)
        if not eff:
            phone = pid.extract_phone_from_text(
                state.user_message
            ) or pid.normalize_tr_phone_digits(state.guest_phone or "")
            if phone:
                candidate = await pid.find_patient_by_phone(
                    session, tenant_id=tenant.id, phone_digits=phone
                )
                if candidate:
                    eff = str(candidate.id)

        user = await get_user(session, eff, tenant.id) if eff else None

        if not user:
            phone = pid.extract_phone_from_text(
                state.user_message
            ) or pid.normalize_tr_phone_digits(state.guest_phone or "")
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
                        "appointments": bridge_map_appointments(
                            [
                                {
                                    "id": str(a.id),
                                    "doctor_name": a.doctor.full_name if a.doctor else "N/A",
                                    "department_name": (
                                        a.department.name if a.department else "N/A"
                                    ),
                                    "start_time": (a.starts_at.isoformat() if a.starts_at else ""),
                                    "end_time": a.ends_at.isoformat() if a.ends_at else "",
                                    "status": (
                                        a.status.value
                                        if hasattr(a.status, "value")
                                        else str(a.status)
                                    ),
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
                "user_message_tr": ("Randevularınızı görmek için kayıtlı cep telefonunuzu yazın."),
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
                "Başlangıç saatini anlayamadım. Örnek: 2026-12-20T14:30:00+03:00 veya "
                "2026-12-20 14:30 biçiminde yazın."
            ),
        }
    if starts_at.tzinfo is None:
        starts_at = starts_at.replace(tzinfo=_TZ_TURKEY)
    slot_start_tr = starts_at.astimezone(_TZ_TURKEY)
    now_tr = datetime.now(_TZ_TURKEY)
    if slot_start_tr < now_tr - timedelta(minutes=5):
        return {
            "success": False,
            "user_message_tr": (
                "Seçtiğiniz saat geçmişte kaldı veya artık uygun değil. "
                "Lütfen ileri bir tarih ve saat seçin."
            ),
        }

    ends_at = starts_at + timedelta(minutes=30)

    async with get_session_factory()() as session:
        tenant = await get_tenant(session, state.tenant_slug)
        if not tenant:
            return {"success": False, "user_message_tr": "Hastane bulunamadı."}

        if hosp_bridge.bridge_is_configured(tenant):
            b = bridge_patient_identity(state)
            if not bridge_identity_ready(b):
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
                    **bridge_identity_payload_fragment(b),
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

        guest_phone = pid.extract_phone_from_text(
            state.user_message
        ) or pid.normalize_tr_phone_digits(state.guest_phone or "")
        guest_name = (
            pid.extract_stated_full_name(state.user_message, state.guest_full_name) or ""
        ).strip()

        eff = effective_patient_user_id(state)
        if not eff and guest_phone:
            candidate = await pid.find_patient_by_phone(
                session, tenant_id=tenant.id, phone_digits=guest_phone
            )
            if candidate is not None:
                eff = str(candidate.id)

        patient = await get_user(session, eff, tenant.id) if eff else None

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
        return {
            "success": True,
            "appointment_id": str(appt.id),
            "user_message_tr": (
                f"Randevunuz oluşturuldu. Doktor: {doc.full_name}. Başlangıç: {st}. "
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

    from tools.slot_params import extract_slot_query_params

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
        starts_iso = f"{day}T{h:02d}:{mi:02d}:{sec:02d}+03:00"

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
        tenant = await get_tenant(session, state.tenant_slug)
        if not tenant:
            return {"success": False, "user_message_tr": "Hastane bulunamadı."}

        if hosp_bridge.bridge_is_configured(tenant):
            b = bridge_patient_identity(state)
            if not bridge_identity_ready(b):
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
                    **bridge_identity_payload_fragment(b),
                    "appointment_id": aid,
                    "user_message": state.user_message[:4000],
                    "conversation_id": (state.conversation_id or "").strip() or None,
                },
            )
            if br is not None:
                return {
                    "success": bool(br.get("success")),
                    "user_message_tr": (br.get("user_message_tr") or "").strip()
                    or "İptal iletildi.",
                }

        import uuid as _uuid

        from sqlalchemy import select as sa_select

        from hospitai.infrastructure.db.models.appointment import Appointment
        from hospitai.infrastructure.db.models.enums import AppointmentStatus

        guest_phone = pid.extract_phone_from_text(
            state.user_message
        ) or pid.normalize_tr_phone_digits(state.guest_phone or "")
        appt_id_str = hosp_bridge.extract_uuid_from_text(state.user_message)

        eff = effective_patient_user_id(state)
        if not eff and guest_phone:
            candidate = await pid.find_patient_by_phone(
                session, tenant_id=tenant.id, phone_digits=guest_phone
            )
            if candidate:
                eff = str(candidate.id)

        appt = None
        if appt_id_str:
            try:
                stmt = sa_select(Appointment).where(
                    Appointment.tenant_id == tenant.id,
                    Appointment.id == _uuid.UUID(appt_id_str),
                )
                appt = (await session.execute(stmt)).scalar_one_or_none()
            except (ValueError, TypeError):
                pass

        if appt is None and guest_phone:
            from datetime import datetime as _dt

            stmt = (
                sa_select(Appointment)
                .where(
                    Appointment.tenant_id == tenant.id,
                    Appointment.guest_contact == guest_phone,
                    Appointment.status != AppointmentStatus.CANCELLED,
                    Appointment.starts_at >= _dt.now(UTC),
                )
                .order_by(Appointment.starts_at.asc())
                .limit(1)
            )
            appt = (await session.execute(stmt)).scalar_one_or_none()

        if appt is None and eff:
            from datetime import datetime as _dt

            stmt = (
                sa_select(Appointment)
                .where(
                    Appointment.tenant_id == tenant.id,
                    Appointment.patient_user_id == _uuid.UUID(eff),
                    Appointment.status != AppointmentStatus.CANCELLED,
                    Appointment.starts_at >= _dt.now(UTC),
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
