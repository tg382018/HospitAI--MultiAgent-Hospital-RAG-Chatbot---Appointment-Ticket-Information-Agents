"""Extract lightweight appointment slot query hints from free text (TR/EN)."""

from __future__ import annotations

import re
from datetime import date, timedelta


def extract_slot_query_params(user_message: str) -> dict[str, str]:
    """Return ``department_name``, ``doctor_name``, ``target_date`` (ISO or empty)."""
    text = (user_message or "").strip()
    out: dict[str, str] = {"department_name": "", "doctor_name": "", "target_date": ""}
    if not text:
        return out

    tl = text.lower()
    today = date.today()
    if re.search(r"\byarın\b|\btomorrow\b", tl):
        out["target_date"] = (today + timedelta(days=1)).isoformat()
    elif re.search(r"\bbugün\b|\btoday\b", tl):
        out["target_date"] = today.isoformat()

    iso = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", text)
    if iso:
        out["target_date"] = iso.group(1)

    doc = re.search(
        r"(?:\bdr\.?\s*|\bdoktoru?\s+)([A-Za-zÇĞİÖŞÜçğıöşüa-zı\s\.]{2,60})",
        text,
        re.IGNORECASE,
    )
    if doc:
        out["doctor_name"] = re.sub(r"\s+", " ", doc.group(1).strip()).strip(" .")

    dept_triggers: list[tuple[str, str]] = [
        ("kardiyo", "Kardiyoloji"),
        ("kalp", "Kardiyoloji"),
        ("cardio", "CARDIO"),
        ("nöro", "Nöroloji"),
        ("nöroloji", "Nöroloji"),
        ("noroloji", "Nöroloji"),
        ("neuro", "NEURO"),
        ("ortopedi", "Ortopedi"),
        ("göz", "Göz"),
        ("dahiliye", "Dahiliye"),
    ]
    for needle, label in dept_triggers:
        if needle in tl:
            out["department_name"] = label
            break

    return out
