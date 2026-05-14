"""LangGraph node callables — tool-augmented agent architecture.

Flow:
    input_guardrail → agent_node ⟷ tool_executor_node → output_guardrail

The LLM decides which tools to call and extracts structured parameters
directly from the user message — no regex keyword matching.
"""

from __future__ import annotations

import dataclasses
import json
from datetime import date, timedelta
from typing import Any

import structlog
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from hospitai_agent.graph.prompts import AGENT_SYSTEM_PROMPT
from hospitai_agent.graph.registry import get_workflow_tools
from hospitai_agent.graph.state_types import (
    GraphState,
    chat_state_to_graph_state,
    graph_state_to_chat_state,
)
from hospitai_agent.graph.tools_schema import APPOINTMENT_TOOLS, COMPLAINT_TOOLS, TOOLS
from hospitai_agent.llm.client import get_llm
from hospitai_agent.llm.profile import get_llm_profile, merge_llm_profile
from hospitai_agent.safety import output_safety_check, safety_check

log = structlog.get_logger(__name__)

_MAX_LOOPS = 5


# ---------------------------------------------------------------------------
# Guardrails
# ---------------------------------------------------------------------------


async def input_guardrail(state: GraphState) -> GraphState:
    cs = graph_state_to_chat_state(state)
    cs = await safety_check(cs)
    return chat_state_to_graph_state(cs)


async def output_guardrail(state: GraphState) -> GraphState:
    cs = graph_state_to_chat_state(state)
    cs = await output_safety_check(cs)
    new_state = chat_state_to_graph_state(cs)

    # Derive intent from which tools were called (for logging / UI)
    new_state["intent"] = _derive_intent(state)

    # Stream the final quality+safety-verified response — only here, after all
    # checks pass, so what the user sees always matches the final message.
    try:
        from langgraph.config import get_stream_writer

        writer = get_stream_writer()
    except Exception:
        writer = None

    if writer is not None:
        final_response = (new_state.get("response") or "").strip()
        if final_response:
            writer({"type": "token", "text": final_response})

    return new_state


# ---------------------------------------------------------------------------
# Agent node — LLM with tool-calling
# ---------------------------------------------------------------------------


async def agent_node(state: GraphState) -> GraphState:
    """Call the LLM. It may request tool calls or produce the final response."""
    if state["safety_flag"] and state["response"]:
        return state

    profile = merge_llm_profile(get_llm_profile(), state.get("llm_overrides") or None)

    # Build the full message list for this LLM call
    messages: list[Any] = [SystemMessage(content=_build_system_prompt(state))]

    # Past conversation turns (from DB memory)
    for msg in state["history"]:
        if msg["role"] == "user":
            messages.append(HumanMessage(content=msg["content"]))
        elif msg["role"] == "assistant":
            messages.append(AIMessage(content=msg["content"]))

    # Current-turn messages (HumanMessage + any tool call/result rounds)
    current_msgs = list(state.get("llm_messages") or [])
    if not current_msgs:
        # First call in this turn — add the user message
        current_msgs.append(HumanMessage(content=state["user_message"]))
    messages.extend(current_msgs)

    # No LLM configured — return a static fallback
    if not (profile.llm_api_key or profile.embedding_api_key):
        state["response"] = (
            "LLM yapılandırılmamış. Lütfen sistem ayarlarını kontrol edin."
        )
        state["pending_tool_calls"] = []
        return state

    llm = get_llm(profile).bind_tools(TOOLS)
    try:
        result = await llm.ainvoke(messages)
    except Exception as exc:
        log.error("agent_node_error", error=str(exc))
        state["response"] = (
            "Üzgünüm, şu anda teknik bir sorun yaşıyorum. "
            "Lütfen daha sonra tekrar deneyin veya hastane bilgi hattını arayın."
        )
        state["pending_tool_calls"] = []
        return state

    tool_calls: list[dict[str, Any]] = getattr(result, "tool_calls", None) or []

    if tool_calls:
        state["pending_tool_calls"] = [
            {"id": tc.get("id", ""), "name": tc["name"], "args": tc.get("args") or {}}
            for tc in tool_calls
        ]
        # Persist current-turn messages so the next agent call sees tool results
        current_msgs.append(result)
        state["llm_messages"] = current_msgs
    else:
        state["response"] = (getattr(result, "content", "") or "").strip()
        state["pending_tool_calls"] = []

    return state


# ---------------------------------------------------------------------------
# Tool executor node — execute LLM-requested tool calls
# ---------------------------------------------------------------------------


async def tool_executor_node(state: GraphState) -> GraphState:
    """Execute pending tool calls and inject results back into the message list."""
    pending = state.get("pending_tool_calls") or []
    if not pending:
        return state

    state["loop_count"] = int(state.get("loop_count") or 0) + 1
    llm_msgs = list(state.get("llm_messages") or [])
    tool_results = list(state.get("tool_results") or [])

    for tc in pending:
        tool_name = tc["name"]
        args = tc.get("args") or {}
        tool_id = tc.get("id") or tool_name

        try:
            result = await _dispatch_tool(state, tool_name, args)
        except Exception as exc:
            log.error("tool_execution_error", tool=tool_name, error=str(exc))
            result = {"success": False, "error": str(exc)}

        log.info("tool_executed", tool=tool_name, success=result.get("success"))
        tool_results.append({"tool": tool_name, "args": args, "result": result})

        # Feed structured result back to the LLM as a ToolMessage
        llm_msgs.append(
            ToolMessage(
                content=_format_result_for_llm(tool_name, result),
                tool_call_id=tool_id,
            )
        )

    state["tool_results"] = tool_results
    state["llm_messages"] = llm_msgs
    state["pending_tool_calls"] = []
    return state


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_system_prompt(state: GraphState) -> str:
    today = date.today()
    tomorrow = today + timedelta(days=1)
    parts = [
        AGENT_SYSTEM_PROMPT,
        f"\nBugünün tarihi: {today.isoformat()} ({today.strftime('%d %B %Y')}). "
        f"Yarın: {tomorrow.isoformat()}. "
        "Tarih içeren ISO datetime oluştururken bu yılı ve tarihi kullan.",
    ]
    if not (state.get("user_id") or "").strip():
        parts.append(
            "Kullanıcı giriş yapmadan yazıyor (misafir). "
            "Randevu veya şikayet işlemleri için ad-soyad ve telefon numarası gereklidir; "
            "kullanıcı bunları mesajında veriyorsa doğrudan araç çağrısına aktar, tekrar sorma."
        )
    return "\n".join(parts)


def _derive_intent(state: GraphState) -> str:
    """Infer intent from which tools were actually called."""
    tools_used = {tr["tool"] for tr in (state.get("tool_results") or [])}
    if tools_used & APPOINTMENT_TOOLS:
        return "appointment"
    if tools_used & COMPLAINT_TOOLS:
        return "complaint"
    if "search_hospital_info" in tools_used:
        return "hospital_info"
    return state.get("intent") or "general"


async def _dispatch_tool(state: GraphState, name: str, args: dict) -> dict:
    """Map an LLM tool call to the corresponding backend WorkflowTools callable."""
    wt = get_workflow_tools()
    cs = graph_state_to_chat_state(state)

    if name == "list_available_slots":
        dept = str(args.get("department_name") or "")
        doc = str(args.get("doctor_name") or "")
        target = _resolve_date(str(args.get("target_date") or ""))
        # Pass structured params via llm_overrides so the backend wrapper skips
        # keyword re-parsing and uses the LLM-extracted values directly.
        overrides = dict(cs.llm_overrides)
        overrides["slot_params"] = {"department_name": dept, "doctor_name": doc, "target_date": target}
        cs = dataclasses.replace(cs, llm_overrides=overrides)
        return await wt.list_available_slots(cs)

    if name == "book_appointment":
        starts_at = str(args.get("starts_at") or "")
        doctor = str(args.get("doctor_name") or "")
        dept = str(args.get("department_name") or "")
        p_name = str(args.get("patient_name") or cs.guest_full_name or "")
        p_phone = str(args.get("patient_phone") or cs.guest_phone or "")
        p_tc = str(args.get("patient_national_id") or cs.guest_national_id or "")
        # Pass structured params via llm_overrides — the backend wrapper reads these
        # directly instead of regex-parsing user_message.
        overrides = dict(cs.llm_overrides)
        overrides["book_params"] = {
            "starts_at": starts_at,
            "doctor_name": doctor,
            "department_name": dept,
        }
        cs = dataclasses.replace(
            cs,
            llm_overrides=overrides,
            guest_full_name=p_name,
            guest_phone=p_phone,
            guest_national_id=p_tc,
        )
        return await wt.book_appointment(cs)

    if name == "list_my_appointments":
        p_name = str(args.get("patient_name") or cs.guest_full_name or "")
        p_phone = str(args.get("patient_phone") or cs.guest_phone or "")
        p_tc = str(args.get("patient_national_id") or cs.guest_national_id or "")
        cs = dataclasses.replace(
            cs, guest_full_name=p_name, guest_phone=p_phone, guest_national_id=p_tc
        )
        return await wt.list_user_appointments(cs)

    if name == "cancel_appointment":
        ref = str(args.get("appointment_reference") or "")
        p_name = str(args.get("patient_name") or cs.guest_full_name or "")
        p_phone = str(args.get("patient_phone") or cs.guest_phone or "")
        msg = f"randevu iptal {ref} {p_name} {p_phone}".strip()
        cs = dataclasses.replace(cs, user_message=msg, guest_full_name=p_name, guest_phone=p_phone)
        return await wt.cancel_appointment(cs)

    if name == "create_complaint_ticket":
        subject = str(args.get("subject") or "")
        desc = str(args.get("description") or "")
        p_name = str(args.get("patient_name") or cs.guest_full_name or "")
        p_phone = str(args.get("patient_phone") or cs.guest_phone or "")
        msg = f"{subject}. {desc}".strip(". ")
        cs = dataclasses.replace(cs, user_message=msg, guest_full_name=p_name, guest_phone=p_phone)
        return await wt.create_ticket_from_message(cs, msg)

    if name == "close_complaint_ticket":
        ref = str(args.get("ticket_reference") or "")
        return await wt.close_ticket(cs, ref)

    if name == "list_complaint_tickets":
        ref = str(args.get("ticket_reference") or "")
        if ref:
            cs = dataclasses.replace(cs, user_message=ref)
            return await wt.get_ticket_by_reference(cs)
        return await wt.list_tickets(cs)

    if name == "search_hospital_info":
        query = str(args.get("query") or state["user_message"])
        result = await wt.retrieve_knowledge(cs, query)
        if result.get("success") and (result.get("context") or "").strip():
            state["rag_context"] = result["context"]
            state["rag_used"] = True
            state["sources"] = result.get("sources") or []
        return result

    return {"success": False, "error": f"Bilinmeyen araç: {name}"}


def _resolve_date(value: str) -> str:
    v = (value or "").lower().strip()
    if v in ("bugün", "bugun", "today"):
        return date.today().isoformat()
    if v in ("yarın", "yarin", "tomorrow"):
        return (date.today() + timedelta(days=1)).isoformat()
    return value


def _format_result_for_llm(name: str, result: dict) -> str:
    """Concise, LLM-readable tool result string."""
    if not isinstance(result, dict):
        return str(result)

    # If backend already composed a user-facing Turkish message, use it
    um = result.get("user_message_tr")
    if isinstance(um, str) and um.strip():
        return um.strip()

    if not result.get("success"):
        err = result.get("error") or result.get("message") or "bilinmeyen hata"
        return f"Araç başarısız: {err}"

    if name == "list_available_slots":
        slots = result.get("slots") or []
        if not slots:
            return f"Müsait slot yok ({result.get('date', '')})."
        lines = [f"Müsait slotlar ({result.get('date', '')}, kaynak: {result.get('source', '')}):"]
        for s in slots[:20]:
            lines.append(
                f"  {s.get('start', '')}–{s.get('end', '')} | "
                f"{s.get('doctor', '')} | {s.get('department', '')}"
            )
        return "\n".join(lines)

    if name == "list_my_appointments":
        appts = result.get("appointments") or []
        if not appts:
            return "Kayıtlı randevu yok."
        lines = ["Randevular:"]
        for a in appts[:15]:
            lines.append(
                f"  {a.get('start', '')} — {a.get('doctor', 'N/A')} "
                f"({a.get('department', 'N/A')}) [{a.get('status', '')}]"
            )
        return "\n".join(lines)

    if name in ("book_appointment", "cancel_appointment"):
        return result.get("message") or (
            "İşlem başarılı." if result.get("success") else "İşlem başarısız."
        )

    if name == "list_complaint_tickets":
        tickets = result.get("tickets") or []
        if not tickets:
            return "Kayıtlı talep yok."
        lines = ["Talepler:"]
        for t in tickets[:10]:
            lines.append(
                f"  [{t.get('reference', '')}] {t.get('subject', '')} – {t.get('status', '')}"
            )
        return "\n".join(lines)

    if name == "search_hospital_info":
        ctx = result.get("context") or ""
        return f"Bilgi tabanı:\n{ctx[:4000]}" if ctx else "İlgili bilgi bulunamadı."

    return json.dumps(result, ensure_ascii=False)[:2000]
