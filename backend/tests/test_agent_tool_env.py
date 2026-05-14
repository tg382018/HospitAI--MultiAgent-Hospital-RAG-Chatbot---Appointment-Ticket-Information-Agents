"""Optional LangSmith / Tavily env export."""

from __future__ import annotations

import os

from hospitai.infrastructure.agent_tool_env import apply_optional_agent_env
from hospitai.infrastructure.settings import Settings


def test_apply_optional_agent_env_sets_langchain_and_tavily(monkeypatch) -> None:
    monkeypatch.delenv("LANGCHAIN_API_KEY", raising=False)
    monkeypatch.delenv("LANGCHAIN_TRACING_V2", raising=False)
    monkeypatch.delenv("LANGCHAIN_PROJECT", raising=False)
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)

    s = Settings(
        langchain_api_key="lc-test",
        langchain_tracing_v2=True,
        langchain_project="proj-x",
        tavily_api_key="tv-test",
    )
    apply_optional_agent_env(s)
    assert os.environ["LANGCHAIN_API_KEY"] == "lc-test"
    assert os.environ["LANGCHAIN_TRACING_V2"] == "true"
    assert os.environ["LANGCHAIN_PROJECT"] == "proj-x"
    assert os.environ["TAVILY_API_KEY"] == "tv-test"


def test_apply_optional_skips_empty(monkeypatch) -> None:
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    s = Settings(tavily_api_key="")
    apply_optional_agent_env(s)
    assert "TAVILY_API_KEY" not in os.environ
