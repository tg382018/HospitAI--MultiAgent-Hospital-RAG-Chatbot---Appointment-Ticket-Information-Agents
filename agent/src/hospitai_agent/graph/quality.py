"""RAG grading, optional web augmentation, and post-generation verification (CRAG-lite)."""

from __future__ import annotations

import asyncio
import json
import os
import re
import urllib.error
import urllib.request
from typing import Any, Literal

import structlog
from langchain_core.messages import HumanMessage, SystemMessage

from hospitai_agent.graph.state_types import GraphState
from hospitai_agent.llm_client import get_llm
from hospitai_agent.llm_profile import get_llm_profile, merge_llm_profile

log = structlog.get_logger(__name__)

_WEB_INTENTS = frozenset({"hospital_info", "medical_info", "general"})
_MAX_RAG_GRADE_CHARS = 8000
_MAX_WEB_QUERY_CHARS = 400

# Kısa nezaket / sohbet — RAG ve doğrulama tetiklenmemeli (alakasız FAQ + yanlış red).
_SMALLTALK_CLINICAL = re.compile(
    r"(randevu|şikayet|talep|bölüm|doktor|poliklinik|ağrı|ilaç|tanı|tedavi|"
    r"appointment|complaint|symptom)",
    re.IGNORECASE,
)


def is_smalltalk_message(text: str) -> bool:
    """True for short greetings / courtesy without clinical intent."""
    t = (text or "").strip()
    if not t or len(t) > 260:
        return False
    if _SMALLTALK_CLINICAL.search(t):
        return False
    head = t[:140].lower()
    for a, b in (
        ("ı", "i"),
        ("ğ", "g"),
        ("ü", "u"),
        ("ş", "s"),
        ("ö", "o"),
        ("ç", "c"),
    ):
        head = head.replace(a, b)
    if re.search(
        r"\b(merhaba|selam|slm|hey|hello|hi|gunaydin|iyi\s*gunler|iyi\s*aksamlar)\b",
        head,
    ):
        return True
    if re.search(r"\b(nasil(sin|siniz)?|iyi\s*misin(iz)?|how\s*are\s*you)\b", head):
        return True
    return bool(re.search(r"^\s*(tesekkur|teşekkür|sa[ğg]ol|mersi)\b", head))


def _parse_json_object(text: str) -> dict[str, Any]:
    raw = str(text or "").strip()
    if "```" in raw:
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
        raw = re.sub(r"\s*```$", "", raw)
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        raw = raw[start : end + 1]
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _tavily_snippet_sync(query: str) -> str:
    key = os.environ.get("TAVILY_API_KEY", "").strip()
    if not key:
        return ""
    body = json.dumps(
        {
            "api_key": key,
            "query": query[:_MAX_WEB_QUERY_CHARS],
            "search_depth": "basic",
            "max_results": 4,
            "include_answer": False,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        "https://api.tavily.com/search",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=18) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (
        urllib.error.URLError,
        urllib.error.HTTPError,
        TimeoutError,
        OSError,
        json.JSONDecodeError,
    ) as exc:
        log.warning("tavily_search_failed", error=str(exc))
        return ""
    results = data.get("results") or []
    lines: list[str] = []
    for r in results[:4]:
        title = str(r.get("title") or "").strip()
        content = str(r.get("content") or "").strip()[:450]
        if content:
            prefix = f"{title}: " if title else ""
            lines.append(f"- {prefix}{content}")
    return "\n".join(lines)


async def grade_rag_relevance(state: GraphState) -> GraphState:
    """Drop RAG context if a judge LLM finds it irrelevant (reduces bad-retrieval hallucination)."""
    if is_smalltalk_message(state.get("user_message") or ""):
        return state
    ctx = (state.get("rag_context") or "").strip()
    if not ctx or state.get("safety_flag"):
        return state

    profile = merge_llm_profile(get_llm_profile(), state.get("llm_overrides") or None)
    if not (profile.llm_api_key or profile.embedding_api_key):
        return state

    llm = get_llm(profile)
    excerpt = ctx[:_MAX_RAG_GRADE_CHARS]
    judge = (
        "Aşağıdaki KULLANICI SORUSU ile BİLGİ TABANI ALINTISI verilmiş.\n"
        "Alıntı, soruyu yanıtlamak için yeterince ilgili mi?\n"
        'Yalnızca şu JSON\'u döndür: {"relevant": true veya false}\n'
        "Alıntı tamamen alakasızsa veya soruya hiç değmiyorsa false.\n\n"
        f"SORU:\n{state['user_message'][:2000]}\n\nALINTI:\n{excerpt}"
    )
    try:
        out = await llm.ainvoke(
            [
                SystemMessage(content="Sen bir alaka sınıflandırıcısısın. Sadece geçerli JSON."),
                HumanMessage(content=judge),
            ]
        )
        data = _parse_json_object(str(getattr(out, "content", "") or ""))
        rel = data.get("relevant", True)
        if isinstance(rel, str):
            rel = rel.lower() in ("true", "1", "yes")
        if rel is False:
            state["rag_context"] = ""
            state["rag_used"] = False
            state["sources"] = []
            log.info("rag_context_rejected_by_grade", intent=state.get("intent"))
    except Exception as exc:
        log.warning("rag_grade_failed", error=str(exc))
    return state


async def augment_web_context(state: GraphState) -> GraphState:
    """Optional Tavily web snippet when local RAG is empty (hospital/medical/general only)."""
    if is_smalltalk_message(state.get("user_message") or ""):
        return state
    if state.get("safety_flag"):
        return state
    intent = state.get("intent") or ""
    if intent not in _WEB_INTENTS:
        return state
    if (state.get("rag_context") or "").strip():
        return state

    snippet = await asyncio.to_thread(_tavily_snippet_sync, state["user_message"])
    if snippet.strip():
        state["web_context"] = snippet.strip()
        state["web_used"] = True
        log.info("web_context_augmented", intent=intent, chars=len(snippet))
    return state


def _evidence_block(state: GraphState) -> str:
    parts: list[str] = []
    if (state.get("rag_context") or "").strip():
        parts.append("=== Bilgi tabanı ===\n" + (state["rag_context"] or "")[:6000])
    if (state.get("web_context") or "").strip():
        parts.append("=== Web özeti (doğrulanmamış) ===\n" + (state["web_context"] or "")[:4000])
    for tr in state.get("tool_results") or []:
        if not isinstance(tr, dict):
            continue
        res = tr.get("result")
        if isinstance(res, dict) and res.get("user_message_tr"):
            parts.append(f"=== Araç ({tr.get('tool')}) ===\n{res['user_message_tr'][:2000]}")
    if not parts:
        return "(Doğrudan kanıt metni yok; genel asistan modu.)"
    return "\n\n".join(parts)


def _has_substantive_evidence(state: GraphState) -> bool:
    if (state.get("rag_context") or "").strip():
        return True
    if (state.get("web_context") or "").strip():
        return True
    for tr in state.get("tool_results") or []:
        if not isinstance(tr, dict):
            continue
        res = tr.get("result")
        if isinstance(res, dict) and (res.get("user_message_tr") or res.get("success") is not None):
            return True
    return False


async def verify_response_quality(state: GraphState) -> GraphState:
    """Post-check vs evidence; one strict regen, then a safe fallback if still weak."""
    state.setdefault("verify_should_retry", False)
    state["verify_should_retry"] = False

    if state.get("safety_flag"):
        return state
    resp = (state.get("response") or "").strip()
    if not resp:
        return state

    if is_smalltalk_message(state.get("user_message") or ""):
        return state

    # Randevu / talep: araç sonuçları ve sistem talimatı yanıtı zaten sınırlar; hakem burada
    # sık sık "kanıt yok" diye eğitimli yanıtları (TC isteme, bilgi hattı) yanlış reddediyor.
    intent_early = str(state.get("intent") or "")
    if intent_early in {"appointment", "complaint"}:
        return state

    profile = merge_llm_profile(get_llm_profile(), state.get("llm_overrides") or None)
    if not (profile.llm_api_key or profile.embedding_api_key):
        return state

    if not _has_substantive_evidence(state):
        return state

    regen = int(state.get("regen_count") or 0)
    evidence = _evidence_block(state)

    judge = (
        "Sen bir kalite denetçisisin. Aşağıda KULLANICI SORUSU, KANIT (RAG/web/araç özeti) ve "
        "ASİSTAN YANITI var.\n"
        'Yalnızca JSON ver: {"supported": true/false, "addresses": true/false}\n'
        "- supported: Somut iddialar (tarih, bölüm listesi, rakam, politika) kanıtta yoksa false.\n"
        "- addresses: Yanıt soruyu fiilen yanıtlamıyorsa false.\n"
        "Kanıt yoksa ve yanıt yalnızca genel yönlendirme ise, uydurma yoksa "
        "supported true kabul et.\n"
        "Selam, nasılsın, teşekkür, kısa nezaket: uygun samimi yanıt için her iki alan da true.\n\n"
        f"SORU:\n{state['user_message'][:2000]}\n\nKANIT:\n{evidence[:8000]}\n\nYANIT:\n{resp[:6000]}"
    )
    try:
        llm = get_llm(profile)
        out = await llm.ainvoke(
            [
                SystemMessage(content="Sadece geçerli JSON; başka metin yok."),
                HumanMessage(content=judge),
            ]
        )
        data = _parse_json_object(str(getattr(out, "content", "") or ""))
        supported = data.get("supported", True)
        addresses = data.get("addresses", True)
        if isinstance(supported, str):
            supported = supported.lower() in ("true", "1", "yes")
        if isinstance(addresses, str):
            addresses = addresses.lower() in ("true", "1", "yes")
    except Exception as exc:
        log.warning("verify_judge_failed", error=str(exc))
        return state

    if supported and addresses:
        return state

    if regen < 1:
        state["regen_count"] = regen + 1
        state["strict_grounding"] = True
        state["verify_should_retry"] = True
        state["response"] = ""
        log.info("verify_triggered_regeneration", supported=supported, addresses=addresses)
        return state

    intent = str(state.get("intent") or "")
    if intent == "general":
        state["response"] = (
            "Yanıtı netleştiremedim; devam edebiliriz. Randevu, bölüm/doktor bilgisi veya "
            "şikayet/talep için neye ihtiyacınız olduğunu kısaca yazabilir misiniz?"
        )
    else:
        state["response"] = (
            "Bu soruda size tam güvenilir bir yanıt üretemedim. "
            "Lütfen hastane bilgi hattını arayın veya randevu alarak hekiminize danışın."
        )
    log.info("verify_fallback_after_regen", supported=supported, addresses=addresses)
    return state


def route_after_verify(state: GraphState) -> Literal["generate_response", "output_guardrail"]:
    if state.get("verify_should_retry"):
        return "generate_response"
    return "output_guardrail"
