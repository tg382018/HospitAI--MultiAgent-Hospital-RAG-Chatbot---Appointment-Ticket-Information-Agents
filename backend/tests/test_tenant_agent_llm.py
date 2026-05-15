"""Tests for tenant-scoped agent LLM settings helpers."""

from __future__ import annotations

from types import SimpleNamespace

from llm.profile import LLMProfile, merge_llm_profile

from hospitai.application.tenant_agent_llm import (
    AGENT_LLM_MODEL_KEY,
    AGENT_LLM_TEMPERATURE_KEY,
    AGENT_MAX_HISTORY_KEY,
    effective_max_conversation_history,
    graph_llm_overrides_from_tenant_settings,
    merge_agent_llm_settings,
    tenant_agent_llm_public_fields,
    validate_agent_llm_patch,
)


def test_merge_agent_llm_preserves_other_settings_keys() -> None:
    current = {"rag_retrieval_enabled": False, "other": 1}
    out = merge_agent_llm_settings(
        current,
        {AGENT_LLM_TEMPERATURE_KEY: 0.3},
    )
    assert out["rag_retrieval_enabled"] is False
    assert out["other"] == 1
    assert out[AGENT_LLM_TEMPERATURE_KEY] == 0.3


def test_graph_llm_overrides_mapping() -> None:
    raw = {
        AGENT_LLM_TEMPERATURE_KEY: "0.8",
        AGENT_LLM_MODEL_KEY: "  gpt-test  ",
    }
    ov = graph_llm_overrides_from_tenant_settings(raw)
    assert ov["llm_temperature"] == 0.8
    assert ov["llm_model"] == "gpt-test"


def test_effective_max_history_uses_tenant_when_set() -> None:
    fake_settings = SimpleNamespace(max_conversation_history=12)
    assert effective_max_conversation_history(None, settings=fake_settings) == 12
    assert (
        effective_max_conversation_history({AGENT_MAX_HISTORY_KEY: 3}, settings=fake_settings) == 3
    )


def test_validate_agent_llm_patch_clamps() -> None:
    p = validate_agent_llm_patch(
        {
            AGENT_LLM_TEMPERATURE_KEY: 99.0,
            AGENT_MAX_HISTORY_KEY: 200,
        }
    )
    assert p[AGENT_LLM_TEMPERATURE_KEY] == 2.0
    assert p[AGENT_MAX_HISTORY_KEY] == 50


def test_tenant_agent_llm_public_fields() -> None:
    d = tenant_agent_llm_public_fields(
        {
            AGENT_LLM_TEMPERATURE_KEY: 0.1,
            AGENT_LLM_MODEL_KEY: "x",
            AGENT_MAX_HISTORY_KEY: 7,
        }
    )
    assert d["agent_llm_temperature"] == 0.1
    assert d["agent_llm_model"] == "x"
    assert d["agent_max_conversation_history"] == 7


def test_merge_llm_profile_keeps_api_keys() -> None:
    base = LLMProfile(
        llm_model="base-model",
        llm_api_key="secret",
        llm_base_url="https://api.example",
        llm_temperature=0.2,
        embedding_api_key="emb",
    )
    m = merge_llm_profile(base, {"llm_model": "override", "llm_temperature": 1.4})
    assert m.llm_model == "override"
    assert m.llm_temperature == 1.4
    assert m.llm_api_key == "secret"
    assert m.embedding_api_key == "emb"
