"""Shared state schema for the LangGraph chat workflow."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ChatState:
    """Mutable state threaded through every node in the graph."""

    user_message: str = ""
    tenant_slug: str = ""
    user_role: str = ""
    user_id: str = ""

    intent: str = "unknown"

    rag_context: str = ""
    rag_used: bool = False

    tool_results: list[dict[str, Any]] = field(default_factory=list)

    safety_flag: bool = False
    safety_reason: str = ""

    history: list[dict[str, str]] = field(default_factory=list)

    response: str = ""
    sources: list[str] = field(default_factory=list)
