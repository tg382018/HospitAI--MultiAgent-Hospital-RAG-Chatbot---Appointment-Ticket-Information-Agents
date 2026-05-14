"""Graph routing functions for the tool-augmented agent."""

from __future__ import annotations

from typing import Literal

from hospitai_agent.graph.nodes import _MAX_LOOPS
from hospitai_agent.graph.state_types import GraphState


def route_after_agent(
    state: GraphState,
) -> Literal["tools", "output_guardrail"]:
    """Route after agent_node: execute pending tool calls or finalize response."""
    if state.get("safety_flag"):
        return "output_guardrail"
    pending = state.get("pending_tool_calls") or []
    if pending and int(state.get("loop_count") or 0) < _MAX_LOOPS:
        return "tools"
    return "output_guardrail"
