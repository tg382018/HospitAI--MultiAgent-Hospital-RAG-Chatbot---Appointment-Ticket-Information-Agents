"""LangGraph state shape and ``ChatState`` round-trip."""

from __future__ import annotations

from typing import Any, TypedDict

from hospitai_agent.state import ChatState


class GraphState(TypedDict):
    # Core conversation
    user_message: str
    tenant_slug: str
    user_role: str
    user_id: str
    history: list[dict[str, str]]
    response: str

    # Safety
    safety_flag: bool
    safety_reason: str

    # Output metadata
    intent: str
    sources: list[str]
    rag_used: bool

    # Guest / identity
    llm_overrides: dict[str, Any]
    guest_full_name: str
    guest_phone: str
    guest_email: str
    guest_national_id: str
    conversation_id: str
    verified_patient_user_id: str

    # Tool call loop (agent architecture)
    pending_tool_calls: list[dict[str, Any]]  # LLM-requested, not yet executed
    tool_results: list[dict[str, Any]]         # executed tool results (for audit/logging)
    llm_messages: list[Any]                    # full LangChain messages for current turn
    loop_count: int                            # guard against infinite tool loops

    # RAG (used by search_hospital_info tool)
    rag_context: str
    web_context: str
    web_used: bool


def chat_state_to_graph_state(cs: ChatState) -> GraphState:
    return GraphState(
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
        guest_full_name=cs.guest_full_name,
        guest_phone=cs.guest_phone,
        guest_email=cs.guest_email,
        guest_national_id=cs.guest_national_id,
        conversation_id=cs.conversation_id,
        verified_patient_user_id=cs.verified_patient_user_id,
        web_context=cs.web_context,
        web_used=cs.web_used,
        # agent-loop fields (not on ChatState — init defaults)
        pending_tool_calls=[],
        llm_messages=[],
        loop_count=0,
    )


def graph_state_to_chat_state(gs: GraphState) -> ChatState:
    return ChatState(
        user_message=gs["user_message"],
        tenant_slug=gs["tenant_slug"],
        user_role=gs["user_role"],
        user_id=gs["user_id"],
        intent=gs["intent"],
        rag_context=gs.get("rag_context") or "",
        rag_used=gs.get("rag_used") or False,
        tool_results=gs["tool_results"],
        safety_flag=gs["safety_flag"],
        safety_reason=gs["safety_reason"],
        history=gs["history"],
        response=gs["response"],
        sources=gs["sources"],
        llm_overrides=dict(gs["llm_overrides"]),
        guest_full_name=str(gs.get("guest_full_name") or ""),
        guest_phone=str(gs.get("guest_phone") or ""),
        guest_email=str(gs.get("guest_email") or ""),
        guest_national_id=str(gs.get("guest_national_id") or ""),
        conversation_id=str(gs.get("conversation_id") or ""),
        verified_patient_user_id=str(gs.get("verified_patient_user_id") or ""),
        web_context=gs.get("web_context") or "",
        web_used=bool(gs.get("web_used")),
    )
