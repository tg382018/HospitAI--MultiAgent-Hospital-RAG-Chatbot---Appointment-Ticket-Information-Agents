"""Intent classification node for the chat workflow."""

from __future__ import annotations

import json
import re

from langchain_core.messages import HumanMessage, SystemMessage

from hospitai_agent.llm_client import get_llm
from hospitai_agent.llm_profile import get_llm_profile
from hospitai_agent.state import ChatState

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

_KEYWORD_MAP: list[tuple[str, re.Pattern[str]]] = [
    (
        "appointment",
        re.compile(
            r"\b(randevu|saat|boş|doktor\s+müsait|iptal|değiş|ertele|"
            r"appointment|cancel|reschedule|book|available\s+slot)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "complaint",
        re.compile(
            r"\b(şikayet|sorun|problem|ticket|talep|başvuru|memnuniyetsiz|"
            r"complaint|issue|ticket|problem|dissatisfied)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "hospital_info",
        re.compile(
            r"\b(bölüm|klinik|poliklinik|ziyaret\s+saat|adres|nerede|ulaşım|"
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
    return None


async def llm_classify(text: str) -> str:
    """Use LLM to classify ambiguous messages."""
    profile = get_llm_profile()
    if not (profile.llm_api_key or profile.embedding_api_key):
        return "general"

    llm = get_llm(profile)
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


async def classify_intent(state: ChatState) -> ChatState:
    """Classify user message intent. Fast path: keywords → LLM fallback."""
    intent = keyword_classify(state.user_message)
    if intent is None:
        intent = await llm_classify(state.user_message)
    state.intent = intent
    return state
