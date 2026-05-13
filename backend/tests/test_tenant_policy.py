"""Unit tests for tenant policy JSON merge helpers."""

from __future__ import annotations

from types import SimpleNamespace

from hospitai.application.tenant_policy import (
    RAG_RETRIEVAL_ENABLED_KEY,
    default_policy,
    effective_policy,
    merge_policy_patch,
    rag_retrieval_enabled,
)


def test_default_policy_has_rag_flag() -> None:
    d = default_policy()
    assert d[RAG_RETRIEVAL_ENABLED_KEY] is True


def test_effective_policy_false_from_tenant() -> None:
    t = SimpleNamespace(settings={RAG_RETRIEVAL_ENABLED_KEY: False})
    assert rag_retrieval_enabled(t) is False


def test_merge_policy_preserves_unknown_keys() -> None:
    current = {"custom": 1, RAG_RETRIEVAL_ENABLED_KEY: True}
    merged = merge_policy_patch(current, {RAG_RETRIEVAL_ENABLED_KEY: False})
    assert merged["custom"] == 1
    assert merged[RAG_RETRIEVAL_ENABLED_KEY] is False


def test_effective_policy_ignores_unknown_keys_in_output_values() -> None:
    t = SimpleNamespace(settings={"noise": 99, RAG_RETRIEVAL_ENABLED_KEY: False})
    pol = effective_policy(t)
    assert "noise" not in pol
    assert pol[RAG_RETRIEVAL_ENABLED_KEY] is False
