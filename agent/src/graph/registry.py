"""Platform-injected workflow tools (DB, RAG, appointments)."""

from __future__ import annotations

from tools.contracts import ChatWorkflowTools

_workflow_tools: ChatWorkflowTools | None = None


def configure_workflow_tools(tools: ChatWorkflowTools) -> None:
    """Register platform-implemented tools before handling chat traffic."""
    global _workflow_tools
    _workflow_tools = tools
    from graph.builder import invalidate_compiled_graph

    invalidate_compiled_graph()


def get_workflow_tools() -> ChatWorkflowTools:
    if _workflow_tools is None:
        raise RuntimeError(
            "Chat workflow tools are not configured. "
            "Call configure_workflow_tools(...) during application startup."
        )
    return _workflow_tools
