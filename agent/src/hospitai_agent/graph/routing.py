"""Intent → handler name; message heuristics for appointment / complaint tools."""

from __future__ import annotations

import re

from hospitai_agent.graph.state_types import GraphState


def wants_my_appointments_list(text: str) -> bool:
    return bool(
        re.search(
            r"randevularım|randevu\s+listem|mevcut\s+randevu|kay[ıi]tl[ıi]\s+randevu|"
            r"ald[ıi]ğ[ıi]m\s+randevu|my\s+appointments",
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
