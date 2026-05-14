"""Public entrypoints: sync chat result + SSE token stream."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from hospitai_agent.graph.builder import get_compiled_graph
from hospitai_agent.graph.state_types import GraphState
from hospitai_agent.graph.streaming import postprocess_chat_result, sse_line


async def run_chat(
    user_message: str,
    tenant_slug: str,
    user_id: str = "",
    user_role: str = "patient",
    history: list[dict[str, str]] | None = None,
    llm_overrides: dict[str, Any] | None = None,
    *,
    guest_full_name: str = "",
    guest_phone: str = "",
    guest_email: str = "",
    guest_national_id: str = "",
    conversation_id: str = "",
    verified_patient_user_id: str = "",
) -> dict[str, Any]:
    """Run the full chat workflow and return the response dict."""
    graph = get_compiled_graph()

    initial_state = GraphState(
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
        guest_full_name=guest_full_name,
        guest_phone=guest_phone,
        guest_email=guest_email,
        guest_national_id=guest_national_id,
        conversation_id=conversation_id,
        verified_patient_user_id=verified_patient_user_id,
        web_context="",
        web_used=False,
        pending_tool_calls=[],
        llm_messages=[],
        loop_count=0,
    )

    final_state = await graph.ainvoke(initial_state)
    return postprocess_chat_result(dict(final_state))


async def iter_chat_sse(
    *,
    user_message: str,
    tenant_slug: str,
    user_id: str = "",
    user_role: str = "patient",
    history: list[dict[str, str]] | None = None,
    llm_overrides: dict[str, Any] | None = None,
    guest_full_name: str = "",
    guest_phone: str = "",
    guest_email: str = "",
    guest_national_id: str = "",
    conversation_id: str = "",
    verified_patient_user_id: str = "",
) -> AsyncIterator[str]:
    """Run the chat graph with LangGraph custom stream (LLM tokens) + SSE lines."""
    graph = get_compiled_graph()
    initial_state: GraphState = GraphState(
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
        guest_full_name=guest_full_name,
        guest_phone=guest_phone,
        guest_email=guest_email,
        guest_national_id=guest_national_id,
        conversation_id=conversation_id,
        verified_patient_user_id=verified_patient_user_id,
        web_context="",
        web_used=False,
        pending_tool_calls=[],
        llm_messages=[],
        loop_count=0,
    )
    acc: dict[str, Any] = dict(initial_state)
    async for mode, chunk in graph.astream(initial_state, stream_mode=["custom", "updates"]):
        if mode == "custom" and isinstance(chunk, dict) and chunk.get("type") == "token":
            text = chunk.get("text")
            if text:
                yield sse_line("token", {"text": text})
        elif mode == "updates" and isinstance(chunk, dict):
            for _node, delta in chunk.items():
                if isinstance(delta, dict):
                    acc.update(delta)
    packed = postprocess_chat_result(acc)
    out = dict(packed)
    out["message"] = packed["response"]
    yield sse_line("final", out)
