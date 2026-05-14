"""Compile LangGraph ``StateGraph`` and cache a single compiled instance."""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, StateGraph

from hospitai_agent.graph.nodes import (
    classify_intent_node,
    generate_response,
    handle_appointment,
    handle_complaint,
    handle_general,
    handle_hospital_info,
    handle_medical_info,
    input_guardrail,
    output_guardrail,
    retrieve_context,
)
from hospitai_agent.graph.quality import (
    augment_web_context,
    grade_rag_relevance,
    route_after_verify,
    verify_response_quality,
)
from hospitai_agent.graph.routing import route_by_intent
from hospitai_agent.graph.state_types import GraphState

_compiled: Any = None


def invalidate_compiled_graph() -> None:
    global _compiled
    _compiled = None


def invalidate_graph() -> None:
    """Public: drop the compiled graph (e.g. after ``configure_workflow_tools``)."""
    invalidate_compiled_graph()


def build_graph() -> Any:
    """Build and compile the LangGraph chat workflow."""
    graph = StateGraph(GraphState)

    graph.add_node("input_guardrail", input_guardrail)
    graph.add_node("classify_intent", classify_intent_node)
    graph.add_node("retrieve_context", retrieve_context)
    graph.add_node("grade_rag_relevance", grade_rag_relevance)
    graph.add_node("augment_web_context", augment_web_context)
    graph.add_node("handle_appointment", handle_appointment)
    graph.add_node("handle_complaint", handle_complaint)
    graph.add_node("handle_hospital_info", handle_hospital_info)
    graph.add_node("handle_medical_info", handle_medical_info)
    graph.add_node("handle_general", handle_general)
    graph.add_node("generate_response", generate_response)
    graph.add_node("verify_response", verify_response_quality)
    graph.add_node("output_guardrail", output_guardrail)

    graph.set_entry_point("input_guardrail")
    graph.add_edge("input_guardrail", "classify_intent")
    graph.add_conditional_edges(
        "classify_intent",
        route_by_intent,
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
    graph.add_edge("retrieve_context", "grade_rag_relevance")
    graph.add_edge("grade_rag_relevance", "augment_web_context")
    graph.add_edge("augment_web_context", "generate_response")
    graph.add_edge("generate_response", "verify_response")
    graph.add_conditional_edges(
        "verify_response",
        route_after_verify,
        {
            "generate_response": "generate_response",
            "output_guardrail": "output_guardrail",
        },
    )
    graph.add_edge("output_guardrail", END)

    return graph.compile()


def get_compiled_graph() -> Any:
    global _compiled
    if _compiled is None:
        _compiled = build_graph()
    return _compiled
