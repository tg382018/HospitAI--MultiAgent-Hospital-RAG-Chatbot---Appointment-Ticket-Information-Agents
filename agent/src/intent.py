"""Intent classification for routing and analytics.

When an OpenAI key is configured, the **preferred** path is always an LLM
classifier with low temperature — this avoids false positives (e.g. treating
pure greetings like "selam" as complaint flows).
"""

from __future__ import annotations

import json
import re

from langchain_core.messages import HumanMessage, SystemMessage

from llm.client import get_llm
from llm.profile import LLMProfile, get_llm_profile
from state import ChatState

# Low temperature stabilizes routing; separate from conversational LLM temperature.
_INTENT_CLASSIFIER_TEMPERATURE = 0.12

_INTENT_SYSTEM_PROMPT = """\
You are an intent classifier for a hospital AI assistant (Turkish and English).

Classify the **latest user message** (using conversation context only for disambiguation)
into exactly ONE intent:

- appointment    — Booking, cancelling, listing, rescheduling appointments; or clearly
                   continuing an appointment flow (e.g. sharing phone / TC after slots were shown).

- complaint      — User **explicitly** wants to file a complaint, open a formal support ticket,
                   report a substantive service failure, reference a complaint ticket,
                   list/close their complaint tickets — e.g. "şikayet etmek istiyorum",
                   "ticket aç", "TKT-", "memnun değilim" in a substantive complaint sense.

- hospital_info  — Departments (as info), visiting hours, address, directions, parking,
                   cafeteria, insurance/policy **about the hospital** (not clinical advice).

- medical_info   — Symptoms, diagnoses questions, medications, clinical guidance requests.

- general        — Greetings ("selam", "merhaba", "hello", "günaydın"), thanks, farewells,
                   small talk, vague "yardım"/"what can you do", or anything that does **not**
                   clearly fit above.

STRICT rules:
- Pure greetings, thanks, or chitchat with **no** appointment/complaint/hospital-topic content
  → **general** always.
- **Never** output **complaint** for a bare greeting or for "merhaba" / "hey" alone.
- If unsure between **general** and **complaint**, choose **general** unless the user
  clearly intends a complaint/ticket workflow.

Reply with ONLY a JSON object: {"intent": "<intent>", "confidence": 0.0-1.0}
No markdown fences. No explanation."""

_IDENTITY_PATTERN = re.compile(
    r"(?:(?:\+90|0090|0)\s*)?5\d{2}[\s.\-]?\d{3}[\s.\-]?\d{2}[\s.\-]?\d{2}\b"
    r"|5\d{9}\b"
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
            r"\b(şikayet|memnuniyetsiz|memnun\s+değil|detaylı\s+talep|ticket\s+oluştur|"
            r"ticket\s+aç|başvuru\s+yap|problem\s+bildir|"
            r"complaint|dissatisfied)\b|\bTKT-[a-fA-F0-9]{12,32}\b",
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

_VALID_INTENTS = frozenset(
    {"appointment", "complaint", "hospital_info", "medical_info", "general"}
)


def _parse_intent_json(raw: str) -> str | None:
    text = raw.strip()
    # Tolerate rare ```json fences from the model
    if text.startswith("```"):
        text = text.removeprefix("```json").removeprefix("```")
        text = text.removesuffix("```").strip()
    try:
        data = json.loads(text)
        intent = data.get("intent", "general")
        if isinstance(intent, str) and intent in _VALID_INTENTS:
            return intent
    except (json.JSONDecodeError, TypeError):
        pass
    return None


def _format_classification_payload(
    user_message: str,
    history: list[dict[str, str]] | None,
    *,
    max_messages: int = 8,
) -> str:
    """Build a single human message with optional transcript for classification."""
    text = user_message.strip()
    h = history or []
    if not h:
        return text

    lines: list[str] = []
    # Last N chronological messages (truncate long assistant answers lightly)
    for msg in h[-max_messages:]:
        role = msg.get("role", "")
        content = (msg.get("content") or "").strip()
        if not content:
            continue
        label = "User" if role == "user" else "Assistant"
        if len(content) > 900:
            content = content[:900] + "…"
        lines.append(f"{label}: {content}")

    transcript = "\n".join(lines)
    return (
        "Conversation transcript (most recent turns):\n"
        f"{transcript}\n\n"
        "Classify ONLY the intent of this latest user message:\n"
        f"{text}"
    )


def keyword_classify(text: str) -> str | None:
    """Return intent if keyword match is unambiguous, else None (used without LLM keys)."""
    matches = [intent for intent, pattern in _KEYWORD_MAP if pattern.search(text)]
    if len(matches) == 1:
        return matches[0]
    if not matches and _IDENTITY_PATTERN.search(text):
        return "appointment"
    return None


async def llm_classify_turn(
    user_message: str,
    *,
    history: list[dict[str, str]] | None = None,
    profile: LLMProfile | None = None,
) -> str:
    """LLM-only classification (deterministic-ish); falls back to general if no keys."""
    p = profile or get_llm_profile()
    if not (p.llm_api_key or p.embedding_api_key):
        return "general"

    llm = get_llm(p, temperature=_INTENT_CLASSIFIER_TEMPERATURE)
    payload = _format_classification_payload(user_message, history)
    messages = [
        SystemMessage(content=_INTENT_SYSTEM_PROMPT),
        HumanMessage(content=payload),
    ]
    result = await llm.ainvoke(messages)
    raw = (getattr(result, "content", None) or "").strip()
    parsed = _parse_intent_json(raw)
    return parsed if parsed is not None else "general"


async def classify_turn_for_tools(
    user_message: str,
    history: list[dict[str, str]] | None,
    profile: LLMProfile | None = None,
) -> str:
    """Intent used to gate complaint tools on the **first** LLM call of a turn.

    With API keys: always uses the classifier LLM (no keyword shortcut).
    Without keys: keyword heuristics only (degraded mode).
    """
    p = profile or get_llm_profile()
    if p.llm_api_key or p.embedding_api_key:
        return await llm_classify_turn(user_message, history=history, profile=p)

    return keyword_classify(user_message) or "general"


async def llm_classify(text: str, profile: LLMProfile | None = None) -> str:
    """Backward-compatible single-message LLM classify (no history)."""
    return await llm_classify_turn(text, history=None, profile=profile)


async def classify_intent(
    state: ChatState,
    llm_profile: LLMProfile | None = None,
) -> ChatState:
    """Classify user message intent (LLM-first when keys are configured)."""
    p = llm_profile or get_llm_profile()
    if p.llm_api_key or p.embedding_api_key:
        intent = await llm_classify_turn(
            state.user_message,
            history=state.history,
            profile=p,
        )
    else:
        intent = keyword_classify(state.user_message) or "general"
    state.intent = intent
    return state
