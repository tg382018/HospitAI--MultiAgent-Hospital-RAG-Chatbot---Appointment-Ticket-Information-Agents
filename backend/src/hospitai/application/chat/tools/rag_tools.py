"""RAG / knowledge-base chat tools."""

from __future__ import annotations

from typing import Any

import structlog
from state import ChatState

from hospitai.application import rag as rag_svc

log = structlog.get_logger(__name__)


async def retrieve_knowledge_tool(state: ChatState, query: str) -> dict[str, Any]:
    """Retrieve relevant context from tenant's knowledge base."""
    try:
        chunks = await rag_svc.retrieve_context(
            state.tenant_slug,
            query=query,
            n_results=10,
        )

        sources = list(
            {
                c.get("metadata", {}).get("title", "")
                for c in chunks
                if c.get("metadata", {}).get("title")
            }
        )

        texts = [c.get("content") or "" for c in chunks]
        merged = "\n\n".join(t for t in texts if t.strip())

        return {
            "success": True,
            "context": merged,
            "sources": sources,
        }
    except Exception as exc:
        log.warning("rag_retrieval_error", error=str(exc))
        return {"success": False, "error": str(exc)}


async def hospital_info_tool(state: ChatState, query: str) -> dict[str, Any]:
    """Retrieve hospital-specific information from the knowledge base."""
    result = await retrieve_knowledge_tool(state, query)
    if result.get("success") and not result.get("context"):
        result["fallback"] = (
            "Bu konuda bilgi bulunamadı. Lütfen hastane bilgi hattını arayın "
            "veya web sitemizi ziyaret edin."
        )
    return result
