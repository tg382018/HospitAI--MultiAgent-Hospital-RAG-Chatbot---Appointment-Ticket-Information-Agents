"""Shared helpers used across all chat tool modules."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import structlog
from state import ChatState

from hospitai.application import patient_identity as pid

log = structlog.get_logger(__name__)

_TZ_TURKEY = timezone(timedelta(hours=3))


def fmt_dt(value: object) -> str:
    """Format a datetime for the LLM – always in Turkey local time (+03:00)."""
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            return value.astimezone(_TZ_TURKEY).isoformat()
        return value.isoformat()
    return str(value or "")


def guest_contact_ready(state: ChatState) -> bool:
    return bool((state.guest_full_name or "").strip() and (state.guest_phone or "").strip())


def effective_patient_user_id(state: ChatState) -> str:
    u = (state.user_id or "").strip()
    if u:
        return u
    return (state.verified_patient_user_id or "").strip()


def bridge_patient_identity(state: ChatState) -> dict[str, str | None]:
    """Misafir hastane köprüsü için TC ve/veya cep + ad-soyad."""
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


def bridge_identity_ready(b: dict[str, str | None]) -> bool:
    return bool(b.get("full_name")) and bool(b.get("national_id") or b.get("phone"))


def bridge_identity_payload_fragment(b: dict[str, str | None]) -> dict[str, Any]:
    out: dict[str, Any] = {"full_name": b["full_name"]}
    if b.get("national_id"):
        out["national_id"] = b["national_id"]
    if b.get("phone"):
        out["phone"] = b["phone"]
    return out


def bridge_map_appointments(raw: list[Any]) -> list[dict[str, Any]]:
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


def bridge_map_tickets(raw: list[Any]) -> list[dict[str, Any]]:
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


async def get_tenant(session: Any, tenant_slug: str) -> Any:
    from sqlalchemy import select

    from hospitai.infrastructure.db.models.tenant import Tenant

    stmt = select(Tenant).where(Tenant.slug == tenant_slug)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_user(session: Any, user_id: str, tenant_id: uuid.UUID) -> Any:
    from sqlalchemy import select

    from hospitai.infrastructure.db.models.user import User

    try:
        uid = uuid.UUID(user_id)
    except (ValueError, TypeError):
        return None

    stmt = select(User).where(User.id == uid, User.tenant_id == tenant_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()
