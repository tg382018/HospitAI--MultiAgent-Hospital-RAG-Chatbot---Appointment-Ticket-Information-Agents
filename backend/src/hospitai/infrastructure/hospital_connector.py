"""HTTP client for tenant-configured external hospital backends (e.g. integrations/xyz-hospital)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

import httpx
import structlog

log = structlog.get_logger(__name__)


def normalize_base_url(url: str) -> str:
    return url.strip().rstrip("/")


def _auth_headers(api_key: str | None) -> dict[str, str]:
    h: dict[str, str] = {"Accept": "application/json"}
    if api_key:
        h["Authorization"] = f"Bearer {api_key}"
    return h


def _as_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    raise TypeError(f"expected datetime or ISO string, got {type(value)}")


def _department_substr_matches(needle: str, dept_code: str) -> bool:
    """Match lay / TR department wording to upstream codes like CARDIO, NEURO."""
    n = needle.strip().lower()
    c = (dept_code or "").strip().lower()
    if not n:
        return True
    if n in c or c in n:
        return True
    cardio = any(k in n for k in ("kardiyo", "kalp", "kardiyoloji")) and "cardio" in c
    neuro = any(k in n for k in ("nöro", "noroloji", "nöroloji")) and "neuro" in c
    return cardio or neuro


async def fetch_external_doctors(*, base_url: str, api_key: str | None) -> list[dict[str, Any]]:
    norm = normalize_base_url(base_url)
    url = f"{norm}/v1/doctors"
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.get(url, headers=_auth_headers(api_key))
        r.raise_for_status()
        data = r.json()
    if not isinstance(data, list):
        log.warning("external_doctors_unexpected_shape", url=url)
        return []
    return data


async def fetch_external_slots_for_doctor(
    *,
    base_url: str,
    api_key: str | None,
    doctor_code: str,
    for_date: date,
) -> list[dict[str, Any]]:
    norm = normalize_base_url(base_url)
    url = f"{norm}/v1/slots"
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.get(
            url,
            params={"doctor_code": doctor_code, "for_date": for_date.isoformat()},
            headers=_auth_headers(api_key),
        )
        r.raise_for_status()
        data = r.json()
    if not isinstance(data, list):
        log.warning("external_slots_unexpected_shape", url=url, doctor_code=doctor_code)
        return []
    return data


async def list_external_slots_merged(
    *,
    base_url: str,
    api_key: str | None,
    for_date: date,
    doctor_name_substr: str | None,
    department_substr: str | None,
) -> list[dict[str, Any]]:
    """Slots in the same shape as :func:`list_available_slots_for_chat` (platform DB path)."""
    doctors = await fetch_external_doctors(base_url=base_url, api_key=api_key)
    dneedle = (doctor_name_substr or "").strip().lower()
    pneedle = (department_substr or "").strip().lower()

    def _matches(doc: dict[str, Any]) -> bool:
        name = str(doc.get("name") or "")
        dept_code = str(doc.get("department_code") or "")
        if dneedle and dneedle not in name.lower():
            return False
        if not pneedle:
            return True
        return _department_substr_matches(pneedle, dept_code)

    if dneedle or pneedle:
        selected = [d for d in doctors if isinstance(d, dict) and _matches(d)]
    else:
        selected = [d for d in doctors if isinstance(d, dict)]

    out: list[dict[str, Any]] = []
    for doc in selected:
        code = str(doc.get("code") or "")
        if not code:
            continue
        doctor_label = str(doc.get("name") or code)
        dept_label = str(doc.get("department_code") or "N/A")
        raw_slots = await fetch_external_slots_for_doctor(
            base_url=base_url,
            api_key=api_key,
            doctor_code=code,
            for_date=for_date,
        )
        for slot in raw_slots:
            if not isinstance(slot, dict):
                continue
            try:
                start = _as_datetime(slot.get("slot_start"))
                end = _as_datetime(slot.get("slot_end"))
            except (TypeError, ValueError):
                continue
            out.append(
                {
                    "doctor_name": doctor_label,
                    "department_name": dept_label,
                    "start_time": start,
                    "end_time": end,
                }
            )
    out.sort(key=lambda row: row["start_time"])
    return out


async def post_external_appointment(
    *,
    base_url: str,
    api_key: str | None,
    body: dict[str, Any],
) -> dict[str, Any]:
    """POST /v1/appointments on the external system; returns parsed JSON body."""
    norm = normalize_base_url(base_url)
    url = f"{norm}/v1/appointments"
    async with httpx.AsyncClient(timeout=25.0) as client:
        r = await client.post(url, json=body, headers=_auth_headers(api_key))
        r.raise_for_status()
        data = r.json()
    if not isinstance(data, dict):
        raise RuntimeError("external_appointment_response_not_object")
    return data


def new_booking_idempotency_key() -> str:
    return f"hp-{uuid.uuid4()}"
