"""Expose optional LangSmith / Tavily keys to ``os.environ`` for LangChain ecosystem."""

from __future__ import annotations

import os

from hospitai.infrastructure.settings import Settings


def apply_optional_agent_env(settings: Settings) -> None:
    """LangChain / LangSmith and Tavily clients typically read standard env names."""
    if settings.langchain_api_key.strip():
        os.environ["LANGCHAIN_API_KEY"] = settings.langchain_api_key.strip()
    if settings.langchain_tracing_v2:
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
    proj = settings.langchain_project.strip()
    if proj:
        os.environ["LANGCHAIN_PROJECT"] = proj
    if settings.tavily_api_key.strip():
        os.environ["TAVILY_API_KEY"] = settings.tavily_api_key.strip()
