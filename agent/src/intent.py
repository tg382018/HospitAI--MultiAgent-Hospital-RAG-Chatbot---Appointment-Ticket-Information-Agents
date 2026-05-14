"""Intent classification node for the chat workflow."""

from __future__ import annotations

import json
import re

from langchain_core.messages import HumanMessage, SystemMessage

from llm.client import get_llm
from llm.profile import LLMProfile, get_llm_profile
from state import ChatState

_INTENT_SYSTEM_PROMPT = """\
You are an intent classifier for a hospital AI assistant.
Classify the user message into exactly ONE of these intents:
- appointment    (booking, cancelling, listing, rescheduling appointments)
- complaint      (complaints, tickets, follow-ups, issues)
- hospital_info  (departments, doctors, visiting hours, directions, services)
- medical_info   (symptoms, conditions, medication info, general medical questions)
- general        (greetings, thanks, chitchat, anything else)

Reply with ONLY a JSON object: {"intent": "<intent>", "confidence": 0.0-1.0}
No explanation. No markdown. Just the JSON."""

_IDENTITY_PATTERN = re.compile(
    # TR mobile: 05xx / +90 5xx / bare 5xx (10 digits) — user providing identity for booking
    r"(?:(?:\+90|0090|0)\s*)?5\d{2}[\s.\-]?\d{3}[\s.\-]?\d{2}[\s.\-]?\d{2}\b"
    r"|5\d{9}\b"
    # TC kimlik: 11-digit number
    r"|\b[1-9]\d{10}\b",
    re.IGNORECASE,
)

_KEYWORD_MAP: list[tuple[str, re.Pattern[str]]] = [
    (
        "appointment",
        re.compile(
            r"\b(randevu|saat|boş|doktor\s+müsait|iptal|değiş|ertele|unuttum|"
            r"tc\s*kimlik|kimlik\s*no|t\.c\.|"
            r"appointment|cancel|reschedule|book|available\s+slot)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "complaint",
        re.compile(
            r"\b(şikayet|sorun|problem|ticket|talep|başvuru|memnuniyetsiz|referans|"
            r"complaint|issue|dissatisfied)\b|\bTKT-[a-fA-F0-9]{12,32}\b",
            re.IGNORECASE,
        ),
    ),
    (
        "hospital_info",
        re.compile(
            r"\b(bölümler|bölüm|klinik|poliklinik|hastane\s+hakk|ziyaret\s+saat|"
            r"adres|nerede|ulaşım|doktorlar|doktor\s+list|hangi\s+hizmet|"
            r"department|visiting\s+hours|directions|location|address)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "medical_info",
        re.compile(
            r"\b(ağrı|belirti|ilaç|tedavi|rahatsız|hastalık|tansiyon|şeker|"
            r"symptom|medication|treatment|diagnosis|condition|blood\s+pressure)\b",
            re.IGNORECASE,
        ),
    ),
]


def keyword_classify(text: str) -> str | None:
    """Return an intent string if keyword match is unambiguous, else None."""
    matches = [intent for intent, pattern in _KEYWORD_MAP if pattern.search(text)]
    if len(matches) == 1:
        return matches[0]
    if not matches and _IDENTITY_PATTERN.search(text):
        # User is supplying a phone number or TC kimlik — they are almost certainly
        # continuing an appointment or identity-verification flow.
        return "appointment"
    return None


async def llm_classify(text: str, profile: LLMProfile | None = None) -> str:
    """Use LLM to classify ambiguous messages."""
    p = profile or get_llm_profile()
    if not (p.llm_api_key or p.embedding_api_key):
        return "general"

    llm = get_llm(p)
    messages = [
        SystemMessage(content=_INTENT_SYSTEM_PROMPT),
        HumanMessage(content=text),
    ]

    result = await llm.ainvoke(messages)
    try:
        data = json.loads(result.content.strip())
        intent = data.get("intent", "general")
        if intent in {
            "appointment",
            "complaint",
            "hospital_info",
            "medical_info",
            "general",
        }:
            return intent
    except (json.JSONDecodeError, KeyError):
        pass
    return "general"


async def classify_intent(
    state: ChatState,
    llm_profile: LLMProfile | None = None,
) -> ChatState:
    """Classify user message intent. Fast path: keywords → LLM fallback."""
    intent = keyword_classify(state.user_message)
    if intent is None:
        intent = await llm_classify(state.user_message, profile=llm_profile)
    state.intent = intent
    return state
