"""LangGraph workflow: Intent → Route → Tools → RAG → Safety → Response."""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator
from typing import Any, TypedDict

import structlog
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph

from hospitai_agent.intent import classify_intent
from hospitai_agent.llm_client import get_llm
from hospitai_agent.llm_profile import get_llm_profile, merge_llm_profile
from hospitai_agent.safety import output_safety_check, safety_check
from hospitai_agent.state import ChatState
from hospitai_agent.workflow_tools import ChatWorkflowTools

log = structlog.get_logger(__name__)


def _chunk_text(chunk: Any) -> str:
    """Extract plain text from a streamed chat model chunk."""
    content = getattr(chunk, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
        return "".join(parts)
    return ""


def _postprocess_chat_result(final_state: dict[str, Any]) -> dict[str, Any]:
    """Apply source footer and flags (shared by sync + SSE chat)."""
    resp = (final_state.get("response") or "").strip()
    sources = [s for s in (final_state.get("sources") or []) if s]
    rag_used = bool(final_state.get("rag_used"))
    safety_flag = bool(final_state.get("safety_flag"))
    if sources and rag_used and not safety_flag and resp:
        tail = ", ".join(sources[:5])
        if len(sources) > 5:
            tail += f" (+{len(sources) - 5})"
        resp = f"{resp}\n\n— Kaynaklar: {tail}"

    reason = str(final_state.get("safety_reason") or "")
    escalated = reason == "emergency"

    return {
        "response": resp,
        "intent": final_state.get("intent", "unknown"),
        "sources": list(final_state.get("sources") or []),
        "rag_used": rag_used,
        "escalated": escalated,
        "safety_flag": safety_flag,
        "safety_reason": reason,
    }


def _sse_line(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


_SYSTEM_PROMPTS: dict[str, str] = {
    "appointment": (
        "Sen HospitAI hastane asistanısın. Kullanıcının randevu taleplerine yardımcı oluyorsun. "
        "Araç çıktılarında müsait saatleri veya mevcut randevuları açıkça özetle. "
        "Dış hastane bağlantılı tenantlarda slot listesi dış sistemden gelmiş olabilir; "
        "kesin rezervasyon için portal veya randevu hattını yönlendir. "
        "Doktor, bölüm, tarih ve saat bilgisini netleştirmesini iste. "
        "Kesin tanı veya tıbbi tavsiye verme. Her zaman profesyonel ve kibar ol."
    ),
    "complaint": (
        "Sen HospitAI hastane asistanısın. Kullanıcının şikayet/talep oluşturma ve takip "
        "işlemlerine yardımcı oluyorsun. Araç çıktısındaki talep listesini özetle; "
        "boşsa nazikçe belirt. Yeni talep için önce kısa konu ve açıklama iste; "
        "kullanıcı netleştirmeden kayıt açma. Empatik ve çözüm odaklı ol."
    ),
    "hospital_info": (
        "Sen HospitAI hastane asistanısın. Hastane bölümleri, doktorlar, ziyaret saatleri, "
        "ulaşım bilgileri gibi konularda bilgi veriyorsun. Bilgi tabanından gelen bağlamı kullan. "
        "Emin olmadığın bilgileri uydurma; 'bilgi bulunamadı' de."
    ),
    "medical_info": (
        "Sen HospitAI hastane asistanısın. Genel tıbbi bilgi sorularını yanıtlıyorsun. "
        "ASLA kesin tanı koyma, ilaç dozu veya reçete önerme; spesifik tedavi yerine "
        "genel çerçeve ver. Her zaman bir sağlık profesyoneline danışmayı öner. "
        "Bilgi tabanından gelen bağlamı kullan. Bilmediğin konularda dürüst ol."
    ),
    "general": (
        "Sen HospitAI hastane asistanısın. Kullanıcılara hastane hizmetleri konusunda yardımcı "
        "oluyorsun: randevu, şikayet, hastane bilgileri, genel sağlık bilgisi. "
        "Kibar ve profesyonel ol. Tanı veya reçete verme."
    ),
}

_GENERAL_FALLBACK = (
    "Size nasıl yardımcı olabileceğimi açıklayayım:\n"
    "• 🏥 Randevu alma ve yönetme\n"
    "• 📋 Şikayet/talep oluşturma ve takip\n"
    "• 🏢 Hastane bölümleri ve doktor bilgileri\n"
    "• ℹ️ Genel sağlık bilgileri\n\n"
    "Nasıl yardımcı olabilirim?"
)


class _GraphState(TypedDict):
    user_message: str
    tenant_slug: str
    user_role: str
    user_id: str
    intent: str
    rag_context: str
    rag_used: bool
    tool_results: list[dict[str, Any]]
    safety_flag: bool
    safety_reason: str
    history: list[dict[str, str]]
    response: str
    sources: list[str]
    llm_overrides: dict[str, Any]


def _cs_to_gs(cs: ChatState) -> _GraphState:
    return _GraphState(
        user_message=cs.user_message,
        tenant_slug=cs.tenant_slug,
        user_role=cs.user_role,
        user_id=cs.user_id,
        intent=cs.intent,
        rag_context=cs.rag_context,
        rag_used=cs.rag_used,
        tool_results=cs.tool_results,
        safety_flag=cs.safety_flag,
        safety_reason=cs.safety_reason,
        history=cs.history,
        response=cs.response,
        sources=cs.sources,
        llm_overrides=dict(cs.llm_overrides),
    )


def _gs_to_cs(gs: _GraphState) -> ChatState:
    return ChatState(
        user_message=gs["user_message"],
        tenant_slug=gs["tenant_slug"],
        user_role=gs["user_role"],
        user_id=gs["user_id"],
        intent=gs["intent"],
        rag_context=gs["rag_context"],
        rag_used=gs["rag_used"],
        tool_results=gs["tool_results"],
        safety_flag=gs["safety_flag"],
        safety_reason=gs["safety_reason"],
        history=gs["history"],
        response=gs["response"],
        sources=gs["sources"],
        llm_overrides=dict(gs["llm_overrides"]),
    )


_workflow_tools: ChatWorkflowTools | None = None
_graph_instance = None


def configure_workflow_tools(tools: ChatWorkflowTools) -> None:
    """Register platform-implemented tools before handling chat traffic."""
    global _workflow_tools, _graph_instance
    _workflow_tools = tools
    _graph_instance = None


def invalidate_graph() -> None:
    """Drop the compiled graph (e.g. after reconfiguration)."""
    global _graph_instance
    _graph_instance = None


def _tools() -> ChatWorkflowTools:
    if _workflow_tools is None:
        raise RuntimeError(
            "Chat workflow tools are not configured. "
            "Call configure_workflow_tools(...) during application startup."
        )
    return _workflow_tools


async def _input_guardrail(state: _GraphState) -> _GraphState:
    cs = _gs_to_cs(state)
    cs = await safety_check(cs)
    return _cs_to_gs(cs)


async def _classify(state: _GraphState) -> _GraphState:
    if state["safety_flag"]:
        return state
    cs = _gs_to_cs(state)
    profile = merge_llm_profile(get_llm_profile(), cs.llm_overrides or None)
    cs = await classify_intent(cs, llm_profile=profile)
    return _cs_to_gs(cs)


async def _retrieve_context(state: _GraphState) -> _GraphState:
    if state["safety_flag"]:
        return state

    intent = state["intent"]
    if intent not in {"hospital_info", "medical_info", "general"}:
        return state

    cs = _gs_to_cs(state)
    result = await _tools().retrieve_knowledge(cs, state["user_message"])
    if result.get("success") and result.get("context"):
        state["rag_context"] = result["context"]
        state["rag_used"] = True
        state["sources"] = result.get("sources", [])
    return state


def _wants_my_appointments_list(text: str) -> bool:
    return bool(
        re.search(
            r"randevularım|randevu\s+listem|mevcut\s+randevu|kay[ıi]tl[ıi]\s+randevu|"
            r"ald[ıi]ğ[ıi]m\s+randevu|my\s+appointments",
            text,
            re.IGNORECASE,
        )
    )


def _wants_slot_search(text: str) -> bool:
    return bool(
        re.search(
            r"müsait|boş|uygun|slot|saat|tarih|ne\s+zaman|book|available|schedule|"
            r"\d{4}-\d{2}-\d{2}|yarın|bugün|tomorrow|today",
            text,
            re.IGNORECASE,
        )
    )


async def _handle_appointment(state: _GraphState) -> _GraphState:
    cs = _gs_to_cs(state)
    msg = state["user_message"]
    wants_list = _wants_my_appointments_list(msg)
    wants_slots = _wants_slot_search(msg)
    if not wants_list and not wants_slots:
        wants_slots = True

    if wants_list:
        listed = await _tools().list_user_appointments(cs)
        state["tool_results"].append({"tool": "list_appointments", "result": listed})

    if wants_slots:
        slotted = await _tools().list_available_slots(cs)
        state["tool_results"].append({"tool": "list_available_slots", "result": slotted})
    return state


async def _handle_complaint(state: _GraphState) -> _GraphState:
    cs = _gs_to_cs(state)
    result = await _tools().list_tickets(cs)
    state["tool_results"].append({"tool": "list_tickets", "result": result})
    return state


async def _handle_hospital_info(state: _GraphState) -> _GraphState:
    return state


async def _handle_medical_info(state: _GraphState) -> _GraphState:
    return state


async def _handle_general(state: _GraphState) -> _GraphState:
    return state


async def _generate_response(state: _GraphState) -> _GraphState:
    if state["safety_flag"] and state["response"]:
        return state

    intent = state["intent"]
    system_prompt = _SYSTEM_PROMPTS.get(intent, _SYSTEM_PROMPTS["general"])

    messages: list[Any] = [SystemMessage(content=system_prompt)]

    for msg in state["history"]:
        if msg["role"] == "user":
            messages.append(HumanMessage(content=msg["content"]))
        elif msg["role"] == "assistant":
            messages.append(AIMessage(content=msg["content"]))

    if state["rag_context"]:
        context_msg = (
            f"Aşağıdaki bilgi tabanı bağlamını kullanarak yanıt ver:\n\n"
            f"---\n{state['rag_context']}\n---\n\n"
            f"Eğer bağlam soruyu yanıtlamıyorsa, genel bilginle yanıtla ama "
            f"bilgi tabanında olmayan bilgiler için 'emin değilim' de."
        )
        messages.append(SystemMessage(content=context_msg))

    for tr in state["tool_results"]:
        tool_name = tr.get("tool", "")
        result = tr.get("result", {})
        if result.get("success"):
            result_msg = f"Araç sonucu ({tool_name}): {result}"
            messages.append(SystemMessage(content=str(result_msg)))

    messages.append(HumanMessage(content=state["user_message"]))

    profile = merge_llm_profile(get_llm_profile(), state["llm_overrides"] or None)
    try:
        from langgraph.config import get_stream_writer

        writer = get_stream_writer()
    except Exception:
        writer = None

    if not (profile.llm_api_key or profile.embedding_api_key):
        if state["tool_results"]:
            state["response"] = _format_tool_response(state)
        else:
            state["response"] = _GENERAL_FALLBACK
        if writer is not None and state["response"]:
            writer({"type": "token", "text": state["response"]})
        return state

    llm = get_llm(profile)
    try:
        if writer is None:
            result = await llm.ainvoke(messages)
            state["response"] = result.content.strip()
        else:
            parts: list[str] = []
            async for chunk in llm.astream(messages):
                piece = _chunk_text(chunk)
                if piece:
                    parts.append(piece)
                    writer({"type": "token", "text": piece})
            state["response"] = "".join(parts).strip()
    except Exception as exc:
        log.error("llm_response_error", error=str(exc))
        state["response"] = (
            "Üzgünüm, şu anda bir teknik sorun yaşıyorum. "
            "Lütfen daha sonra tekrar deneyin veya hastane bilgi hattını arayın."
        )
        if writer is not None and state["response"]:
            writer({"type": "token", "text": state["response"]})

    return state


async def _output_guardrail(state: _GraphState) -> _GraphState:
    cs = _gs_to_cs(state)
    cs = await output_safety_check(cs)
    return _cs_to_gs(cs)


def _format_tool_response(state: _GraphState) -> str:
    parts: list[str] = []
    for tr in state["tool_results"]:
        result = tr.get("result", {})
        if not result.get("success"):
            parts.append(result.get("error", "Bilinmeyen hata"))
            continue

        tool_name = tr.get("tool", "")
        if tool_name == "list_available_slots":
            slots = result.get("slots", [])
            src = result.get("source", "")
            prefix = "Müsait randevular"
            if src == "external":
                prefix += " (dış hastane bağlantısı)"
            if not slots:
                parts.append(f"{prefix}: {result.get('date', '')} için kayıt bulunamadı.")
            else:
                parts.append(f"{prefix} ({result.get('date', '')}):")
                for s in slots[:10]:
                    line = f"  • {s['doctor']} - {s['department']}: {s['start']} - {s['end']}"
                    parts.append(line)
                if len(slots) > 10:
                    parts.append(f"  ... ve {len(slots) - 10} saat daha")

        elif tool_name == "list_tickets":
            tickets = result.get("tickets", [])
            if not tickets:
                parts.append("Kayıtlı talebiniz bulunmamaktadır.")
            else:
                parts.append("Talepleriniz:")
                for t in tickets:
                    parts.append(f"  • [{t['reference']}] {t['subject']} - {t['status']}")

        elif tool_name == "list_appointments":
            appts = result.get("appointments", [])
            if not appts:
                parts.append("Kayıtlı randevunuz bulunmamaktadır.")
            else:
                parts.append("Randevularınız:")
                for a in appts[:15]:
                    parts.append(
                        f"  • {a.get('start', '')} — {a.get('doctor', 'N/A')} "
                        f"({a.get('department', 'N/A')}) [{a.get('status', '')}]"
                    )
                if len(appts) > 15:
                    parts.append(f"  ... ve {len(appts) - 15} randevu daha")

        elif tool_name == "create_ticket":
            parts.append(result.get("message", "Talep oluşturuldu."))

        else:
            parts.append(str(result))

    return "\n".join(parts) if parts else _GENERAL_FALLBACK


def _route_by_intent(state: _GraphState) -> str:
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


def build_graph() -> StateGraph:
    """Build and compile the LangGraph chat workflow."""
    graph = StateGraph(_GraphState)

    graph.add_node("input_guardrail", _input_guardrail)
    graph.add_node("classify_intent", _classify)
    graph.add_node("retrieve_context", _retrieve_context)
    graph.add_node("handle_appointment", _handle_appointment)
    graph.add_node("handle_complaint", _handle_complaint)
    graph.add_node("handle_hospital_info", _handle_hospital_info)
    graph.add_node("handle_medical_info", _handle_medical_info)
    graph.add_node("handle_general", _handle_general)
    graph.add_node("generate_response", _generate_response)
    graph.add_node("output_guardrail", _output_guardrail)

    graph.set_entry_point("input_guardrail")
    graph.add_edge("input_guardrail", "classify_intent")
    graph.add_conditional_edges(
        "classify_intent",
        _route_by_intent,
        {
            "handle_appointment": "handle_appointment",
            "handle_complaint": "handle_complaint",
            "handle_hospital_info": "handle_hospital_info",
            "handle_medical_info": "handle_medical_info",
            "handle_general": "handle_general",
            "generate_response": "generate_response",
        },
    )
    graph.add_edge("handle_appointment", "generate_response")
    graph.add_edge("handle_complaint", "generate_response")
    graph.add_edge("handle_hospital_info", "retrieve_context")
    graph.add_edge("handle_medical_info", "retrieve_context")
    graph.add_edge("handle_general", "retrieve_context")
    graph.add_edge("retrieve_context", "generate_response")
    graph.add_edge("generate_response", "output_guardrail")
    graph.add_edge("output_guardrail", END)

    return graph.compile()


def _get_graph():
    global _graph_instance
    if _graph_instance is None:
        _graph_instance = build_graph()
    return _graph_instance


async def run_chat(
    user_message: str,
    tenant_slug: str,
    user_id: str = "",
    user_role: str = "patient",
    history: list[dict[str, str]] | None = None,
    llm_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run the full chat workflow and return the response dict."""
    graph = _get_graph()

    initial_state = _GraphState(
        user_message=user_message,
        tenant_slug=tenant_slug,
        user_role=user_role,
        user_id=user_id,
        intent="unknown",
        rag_context="",
        rag_used=False,
        tool_results=[],
        safety_flag=False,
        safety_reason="",
        history=history or [],
        response="",
        sources=[],
        llm_overrides=dict(llm_overrides or {}),
    )

    final_state = await graph.ainvoke(initial_state)
    return _postprocess_chat_result(dict(final_state))


async def iter_chat_sse(
    *,
    user_message: str,
    tenant_slug: str,
    user_id: str = "",
    user_role: str = "patient",
    history: list[dict[str, str]] | None = None,
    llm_overrides: dict[str, Any] | None = None,
) -> AsyncIterator[str]:
    """Run the chat graph with LangGraph custom stream (LLM tokens) + SSE lines."""
    graph = _get_graph()
    initial_state: _GraphState = _GraphState(
        user_message=user_message,
        tenant_slug=tenant_slug,
        user_role=user_role,
        user_id=user_id,
        intent="unknown",
        rag_context="",
        rag_used=False,
        tool_results=[],
        safety_flag=False,
        safety_reason="",
        history=history or [],
        response="",
        sources=[],
        llm_overrides=dict(llm_overrides or {}),
    )
    acc: dict[str, Any] = dict(initial_state)
    async for mode, chunk in graph.astream(initial_state, stream_mode=["custom", "updates"]):
        if mode == "custom" and isinstance(chunk, dict) and chunk.get("type") == "token":
            text = chunk.get("text")
            if text:
                yield _sse_line("token", {"text": text})
        elif mode == "updates" and isinstance(chunk, dict):
            for _node, delta in chunk.items():
                if isinstance(delta, dict):
                    acc.update(delta)
    packed = _postprocess_chat_result(acc)
    out = dict(packed)
    out["message"] = packed["response"]
    yield _sse_line("final", out)
