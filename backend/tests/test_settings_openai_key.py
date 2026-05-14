"""OPENAI_API_KEY unified propagation into LLM / embedding keys."""

from __future__ import annotations

from hospitai.infrastructure.settings import Settings


def test_openai_unified_key_fills_both_when_empty() -> None:
    s = Settings(
        openai_api_key="sk-unified-test",
        llm_api_key="",
        embedding_api_key="",
    )
    assert s.llm_api_key == "sk-unified-test"
    assert s.embedding_api_key == "sk-unified-test"


def test_explicit_llm_key_not_overwritten_by_openai() -> None:
    s = Settings(
        openai_api_key="sk-openai",
        llm_api_key="sk-llm-only",
        embedding_api_key="",
    )
    assert s.llm_api_key == "sk-llm-only"
    assert s.embedding_api_key == "sk-openai"


def test_explicit_embedding_not_overwritten() -> None:
    s = Settings(
        openai_api_key="sk-openai",
        llm_api_key="",
        embedding_api_key="sk-emb-only",
    )
    assert s.llm_api_key == "sk-openai"
    assert s.embedding_api_key == "sk-emb-only"
