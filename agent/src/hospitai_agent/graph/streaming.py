"""SSE helpers, stream chunk parsing, final response post-processing."""

from __future__ import annotations

import json
from typing import Any


def chunk_text(chunk: Any) -> str:
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


def postprocess_chat_result(final_state: dict[str, Any]) -> dict[str, Any]:
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


def sse_line(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
