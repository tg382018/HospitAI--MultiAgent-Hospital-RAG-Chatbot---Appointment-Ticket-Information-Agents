"""Intent → handler name; message heuristics for appointment / complaint tools."""

from __future__ import annotations

import re

from hospitai_agent.graph.state_types import GraphState


def wants_my_appointments_list(text: str) -> bool:
    return bool(
        re.search(
            r"randevularım|randevu\s+listem|mevcut\s+randevu|kay[ıi]tl[ıi]\s+randevu|"
            r"ald[ıi]ğ[ıi]m\s+randevu|randevum\b|randyevum\b|"
            r"my\s+appointments",
            text,
            re.IGNORECASE,
        )
    )


def wants_slot_search(text: str) -> bool:
    return bool(
        re.search(
            r"müsait|boş|uygun|slot|saat|tarih|ne\s+zaman|book|available|schedule|"
            r"\d{4}-\d{2}-\d{2}|yarın|bugün|tomorrow|today",
            text,
            re.IGNORECASE,
        )
    )


def wants_book_appointment(text: str) -> bool:
    return bool(
        re.search(
            r"randevu\s+al|randevu\s+oluştur|rezervasyon|r(?:andevu)?\s*ay[ıi]r|"
            r"book\s+(an\s+)?appointment|schedule\s+appointment|"
            r"bu\s+saat(?:e|i)?\s+al|slotu\s+ay[ıi]r",
            text,
            re.IGNORECASE,
        )
    )


def wants_cancel_appointment(text: str) -> bool:
    return bool(
        re.search(
            r"randevu(?:yu|m|yu)?\s+iptal|iptal\s+et|iptal\s+edeceğim|iptal\s+edecem|"
            r"iptal\s+istiyorum|randevu\s+iptali|cancel\s+(my\s+)?appointment|"
            r"appointment\s+cancel",
            text,
            re.IGNORECASE,
        )
    )


def has_tc_kimlik_candidate(text: str) -> bool:
    """11 haneli aday (doğrulama aracında checksum kontrol edilir)."""
    return bool(re.search(r"\b\d{11}\b", text or ""))


def has_tr_phone_candidate(text: str) -> bool:
    """Metinde TR cep telefonu biçimi (05xx / +90 5xx / 5xx ile başlayan 10 hane)."""
    t = text or ""
    phone_like = r"(?:\+90|0090|0)?\s*5\d{2}[\s.-]?\d{3}[\s.-]?\d{2}[\s.-]?\d{2}\b"
    if re.search(phone_like, t, re.IGNORECASE):
        return True
    d = re.sub(r"\D", "", t)
    return bool(re.search(r"5\d{9}", d))


def wants_complaint_ticket_list(text: str) -> bool:
    return bool(
        re.search(
            r"taleplerim|şikayetlerim|tüm\s+talep|ticket\s+list|listele|"
            r"my\s+tickets|open\s+tickets|açık\s+talep",
            text,
            re.IGNORECASE,
        )
    )


def wants_new_complaint_ticket(text: str) -> bool:
    """User wants to open a new ticket (not only list or reference lookup)."""
    return bool(
        re.search(
            r"şikayet\s+oluştur|talep\s+oluştur|başvuru\s+yap|"
            r"yeni\s+(şikayet|talep|başvuru)|"
            r"oluşturmak\s+istiyorum|kaydı\s+aç|bildirmek\s+istiyorum|"
            r"(create|open|file)\s+(a\s+)?(complaint|ticket)",
            text,
            re.IGNORECASE,
        )
    )


def route_by_intent(state: GraphState) -> str:
    if state["safety_flag"]:
        return "generate_response"

    intent = state["intent"]
    route_map = {
        "appointment": "handle_appointment",
        "complaint": "handle_complaint",
        "hospital_info": "handle_hospital_info",
        "medical_info": "handle_medical_info",
        "general": "handle_general",
    }
    return route_map.get(intent, "handle_general")
