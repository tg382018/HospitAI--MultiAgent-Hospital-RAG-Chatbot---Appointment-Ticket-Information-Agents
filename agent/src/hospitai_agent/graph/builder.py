"""Compile LangGraph ``StateGraph`` and cache a single compiled instance."""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, StateGraph

from hospitai_agent.graph.nodes import (
    agent_node,
    input_guardrail,
    output_guardrail,
    tool_executor_node,
)
from hospitai_agent.graph.routing import route_after_agent
from hospitai_agent.graph.state_types import GraphState

_compiled: Any = None


def invalidate_compiled_graph() -> None:
    global _compiled
    _compiled = None


def invalidate_graph() -> None:
    """Public: drop the compiled graph (e.g. after ``configure_workflow_tools``)."""
    invalidate_compiled_graph()


def build_graph() -> Any:
    """Build and compile the tool-augmented LangGraph chat workflow.

    input_guardrail → agent ⟷ tools (loop up to _MAX_LOOPS) → output_guardrail
    """
    graph = StateGraph(GraphState)

    graph.add_node("input_guardrail", input_guardrail)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tool_executor_node)
    graph.add_node("output_guardrail", output_guardrail)

    graph.set_entry_point("input_guardrail")
    graph.add_edge("input_guardrail", "agent")

    graph.add_conditional_edges(
        "agent",
        route_after_agent,
        {
            "tools": "tools",
            "output_guardrail": "output_guardrail",
        },
    )

    graph.add_edge("tools", "agent")
    graph.add_edge("output_guardrail", END)

    return graph.compile()


def get_compiled_graph() -> Any:
    global _compiled
    if _compiled is None:
        _compiled = build_graph()
    return _compiled
