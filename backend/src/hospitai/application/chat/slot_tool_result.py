"""Stable slot-listing tool shape + Turkish user-facing summaries (plan adım 2)."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

SlotToolOutcome = Literal[
    "slots_found",
    "no_slots_broad",
    "no_slots_filtered",
    "no_matching_doctors_external",
    "external_catalog_empty",
    "tenant_not_found",
    "upstream_transport",
    "date_required",
    "past_date",
    "invalid_date",
]


def format_slot_lines(slots: list[dict[str, Any]], *, max_visible: int = 10) -> list[str]:
    lines: list[str] = []
    for s in slots[:max_visible]:
        doc = str(s.get("doctor", "") or "")
        dep = str(s.get("department", "") or "")
        start = str(s.get("start", "") or "")
        end = str(s.get("end", "") or "")
        lines.append(f"• {doc} — {dep}: {start} – {end}")
    if len(slots) > max_visible:
        lines.append(f"… ve {len(slots) - max_visible} saat daha")
    return lines


def user_message_slots_found(
    *,
    date_iso: str,
    source: Literal["internal", "external"],
    slots: list[dict[str, Any]],
) -> str:
    head = "Müsait randevu saatleri"
    if source == "external":
        head += " (dış hastane bağlantısı)"
    head += f" — {date_iso}:"
    body = format_slot_lines(slots)
    return head + ("\n" + "\n".join(body) if body else "\n(kayıt yok)")


def user_message_no_slots_filtered(*, date_iso: str) -> str:
    return (
        f"{date_iso} tarihi için aradığınız doktor veya bölüm kriterlerine uygun "
        "müsait randevu saati bulunamadı. Tarihi veya doktor/bölüm adını değiştirip "
        "yeniden deneyebilir veya randevu hattını arayabilirsiniz."
    )


def user_message_no_slots_broad(*, date_iso: str, source: Literal["internal", "external"]) -> str:
    src = (
        "dış randevu sisteminde"
        if source == "external"
        else "hastane kayıtlarında"
    )
    return (
        f"{date_iso} tarihi için {src} listelenecek müsait randevu saati bulunamadı. "
        "Başka bir gün deneyebilir, kriterlerinizi genişletebilir veya randevu hattını "
        "arayabilirsiniz."
    )


def user_message_no_matching_doctors_external(*, date_iso: str) -> str:
    return (
        f"{date_iso} için aradığınız doktor veya bölüm adına uygun kayıt dış sistemde "
        "bulunamadı. Yazımı kontrol edin veya randevu hattından yardım alın."
    )


def user_message_external_catalog_empty(*, date_iso: str) -> str:
    return (
        f"Dış randevu sisteminden {date_iso} için doktor/slot bilgisi alınamadı "
        "(liste boş veya servis yanıtı eksik). Lütfen daha sonra tekrar deneyin veya "
        "randevu hattını arayın."
    )


def wrap_slot_tool_success(
    *,
    day: date,
    source: Literal["internal", "external"],
    serialized_slots: list[dict[str, Any]],
    ext_meta: dict[str, Any] | None,
    filter_department: str,
    filter_doctor: str,
) -> dict[str, Any]:
    """Build the dict returned by ``list_available_slots_tool`` on success paths."""
    date_iso = day.isoformat()
    has_text_filter = bool(filter_department.strip() or filter_doctor.strip())

    if serialized_slots:
        outcome: SlotToolOutcome = "slots_found"
        user_tr = user_message_slots_found(
            date_iso=date_iso, source=source, slots=serialized_slots
        )
    elif source == "external" and ext_meta is not None:
        matched = int(ext_meta.get("matched_doctors") or 0)
        filter_applied = bool(ext_meta.get("filter_applied"))
        upstream = int(ext_meta.get("upstream_doctor_count") or 0)
        if matched == 0 and filter_applied:
            outcome = "no_matching_doctors_external"
            user_tr = user_message_no_matching_doctors_external(date_iso=date_iso)
        elif matched == 0 and upstream == 0:
            outcome = "external_catalog_empty"
            user_tr = user_message_external_catalog_empty(date_iso=date_iso)
        else:
            outcome = "no_slots_broad"
            user_tr = user_message_no_slots_broad(date_iso=date_iso, source=source)
    elif has_text_filter:
        outcome = "no_slots_filtered"
        user_tr = user_message_no_slots_filtered(date_iso=date_iso)
    else:
        outcome = "no_slots_broad"
        user_tr = user_message_no_slots_broad(date_iso=date_iso, source=source)

    return {
        "success": True,
        "slot_outcome": outcome,
        "user_message_tr": user_tr,
        "date": date_iso,
        "slots": serialized_slots,
        "count": len(serialized_slots),
        "source": source,
    }


def wrap_slot_tool_error(
    *,
    outcome: SlotToolOutcome,
    error: str,
    user_message_tr: str | None = None,
) -> dict[str, Any]:
    return {
        "success": False,
        "slot_outcome": outcome,
        "error": error,
        "user_message_tr": user_message_tr or error,
        "slots": [],
        "count": 0,
    }
