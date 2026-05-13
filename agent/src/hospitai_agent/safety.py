"""Input & output safety guardrails for the chat workflow."""

from __future__ import annotations

import re

from langchain_core.messages import HumanMessage, SystemMessage

from hospitai_agent.llm_client import get_llm
from hospitai_agent.llm_profile import get_llm_profile
from hospitai_agent.state import ChatState

_EMERGENCY_KEYWORDS = re.compile(
    r"\b(ambulan[sc]|acil|intihar|kendine\s+z[ea]r\s+ver|kalp\s+kriz|"
    r"nefes\s+alam[iı]yo|bay[iı]l|bilin[cç]\s+kayb|şiddetli\s+kanama|"
    r"felç|inme|stroke|anafilaksi|boğuluyorum|"
    r"emergency|ambulance|suicide|chest\s+pain|unconscious|severe\s+bleeding)\b",
    re.IGNORECASE,
)

_INJECTION_PATTERNS = re.compile(
    r"(ignore\s+(all\s+)?previous\s+instructions|"
    r"you\s+are\s+now\s+|system\s*prompt|"
    r"override\s+your\s+rules|jailbreak|DAN\s+mode|"
    r"unfiltered\s+mode|"
    r"önceki\s+talimatları\s+yok\s+say|"
    r"disregard\s+the\s+above|"
    r"reveal\s+(your\s+)?(system\s+)?prompt|"
    r"developer\s+mode\s+enabled)",
    re.IGNORECASE,
)


def check_emergency(text: str) -> str | None:
    """Return an escalation message if emergency keywords are detected."""
    if _EMERGENCY_KEYWORDS.search(text):
        return (
            "Acil bir durum tespit edildi. Lütfen derhal 112 Acil Servisi arayın "
            "veya en yakın hastanenin acil servisine başvurun. Bu sohbet acil tıbbi "
            "durumlar için uygun değildir."
        )
    return None


def check_injection(text: str) -> bool:
    """Return True if prompt injection patterns are detected."""
    return bool(_INJECTION_PATTERNS.search(text))


def check_pii(text: str) -> list[str]:
    """Return a list of detected PII types (basic heuristic)."""
    findings: list[str] = []
    if re.search(r"\b[1-9]\d{10}\b", text):
        findings.append("national_id")
    if re.search(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{1,7}\b", text):
        findings.append("credit_card")
    return findings


_SAFETY_SYSTEM_PROMPT = """You are a safety reviewer for a hospital AI assistant.
Evaluate whether the following AI response is safe and appropriate.
Reply with exactly one of:
- SAFE — if the response is medically safe and does not give harmful advice.
- UNSAFE:<reason> — if the response is potentially harmful (e.g., diagnosis, prescription).

Respond in English. Be conservative."""


async def llm_output_safety_check(response: str) -> tuple[bool, str]:
    """Use LLM to verify response safety. Returns (is_safe, reason)."""
    profile = get_llm_profile()
    if not (profile.llm_api_key or profile.embedding_api_key):
        return True, ""

    llm = get_llm(profile)
    messages = [
        SystemMessage(content=_SAFETY_SYSTEM_PROMPT),
        HumanMessage(content=response),
    ]

    result = await llm.ainvoke(messages)
    verdict = result.content.strip()

    if verdict.startswith("SAFE"):
        return True, ""
    if verdict.startswith("UNSAFE"):
        reason = verdict.split(":", 1)[1].strip() if ":" in verdict else "Flagged by safety check"
        return False, reason
    return True, ""


async def safety_check(state: ChatState) -> ChatState:
    """Run input safety checks. Sets state.safety_flag if issues found."""
    msg = state.user_message

    escalation = check_emergency(msg)
    if escalation:
        state.safety_flag = True
        state.safety_reason = "emergency"
        state.response = escalation
        return state

    if check_injection(msg):
        state.safety_flag = True
        state.safety_reason = "injection"
        state.response = (
            "Güvenlik nedeniyle bu istek işlenemiyor. "
            "Lütfen hastane hizmetleriyle ilgili normal bir soru sorun."
        )
        return state

    pii = check_pii(msg)
    if pii:
        state.safety_flag = True
        state.safety_reason = f"pii_blocked:{','.join(pii)}"
        state.response = (
            "Kimlik numarası veya kart bilgisi gibi hassas verileri "
            "lütfen bu sohbet üzerinden paylaşmayın. Bu bilgileri yalnızca "
            "hastanemizin güvenli kanalları veya yüz yüze iletin."
        )
        return state

    return state


async def output_safety_check(state: ChatState) -> ChatState:
    """Run LLM-based output safety check."""
    if not state.response:
        return state

    is_safe, reason = await llm_output_safety_check(state.response)
    if not is_safe:
        state.safety_flag = True
        state.safety_reason = f"unsafe_output:{reason}"
        state.response = (
            "Bu konuda size yardımcı olamıyorum. Lütfen bir sağlık profesyoneline danışın. "
            "Genel bilgi almak için hastanemizin bilgi hattını arayabilirsiniz."
        )
    return state
