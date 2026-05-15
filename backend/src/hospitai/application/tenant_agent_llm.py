"""Tenant-scoped LLM / chat limits stored in ``Tenant.settings`` JSONB."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator

from hospitai.infrastructure.settings import Settings, get_settings

AGENT_LLM_TEMPERATURE_KEY = "agent_llm_temperature"
AGENT_LLM_MODEL_KEY = "agent_llm_model"
AGENT_MAX_HISTORY_KEY = "agent_max_conversation_history"

_AGENT_PATCH_KEYS = frozenset(
    {
        AGENT_LLM_TEMPERATURE_KEY,
        AGENT_LLM_MODEL_KEY,
        AGENT_MAX_HISTORY_KEY,
    }
)


class TenantAgentLLMPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_llm_temperature: float | None = None
    agent_llm_model: str | None = None
    agent_max_conversation_history: int | None = None

    @field_validator("agent_llm_temperature")
    @classmethod
    def _clamp_temp(cls, v: float | None) -> float | None:
        if v is None:
            return None
        return max(0.0, min(2.0, float(v)))

    @field_validator("agent_llm_model")
    @classmethod
    def _trim_model(cls, v: str | None) -> str | None:
        if v is None:
            return None
        t = v.strip()[:128]
        return t or None

    @field_validator("agent_max_conversation_history")
    @classmethod
    def _clamp_hist(cls, v: int | None) -> int | None:
        if v is None:
            return None
        return max(1, min(50, int(v)))


def merge_agent_llm_settings(
    current: dict[str, Any] | None,
    patch: dict[str, Any],
) -> dict[str, Any]:
    """Shallow-merge only agent LLM keys into full tenant.settings dict."""
    out = dict(current) if isinstance(current, dict) else {}
    for k, v in patch.items():
        if k in _AGENT_PATCH_KEYS:
            out[k] = v
    return out


def graph_llm_overrides_from_tenant_settings(raw: dict[str, Any] | None) -> dict[str, Any]:
    """Map tenant.settings → kwargs for ``merge_llm_profile`` (global API keys unchanged)."""
    if not raw:
        return {}
    out: dict[str, Any] = {}
    if AGENT_LLM_TEMPERATURE_KEY in raw and raw[AGENT_LLM_TEMPERATURE_KEY] is not None:
        try:
            t = float(raw[AGENT_LLM_TEMPERATURE_KEY])
            out["llm_temperature"] = max(0.0, min(2.0, t))
        except (TypeError, ValueError):
            pass
    if raw.get(AGENT_LLM_MODEL_KEY):
        model = str(raw[AGENT_LLM_MODEL_KEY]).strip()[:128]
        if model:
            out["llm_model"] = model
    return out


def effective_max_conversation_history(
    tenant_settings: dict[str, Any] | None,
    *,
    settings: Settings | None = None,
) -> int:
    s = settings or get_settings()
    default = s.max_conversation_history
    if not tenant_settings or AGENT_MAX_HISTORY_KEY not in tenant_settings:
        return default
    v = tenant_settings.get(AGENT_MAX_HISTORY_KEY)
    try:
        n = int(v)
    except (TypeError, ValueError):
        return default
    return max(1, min(50, n))


def validate_agent_llm_patch(patch: dict[str, Any]) -> dict[str, Any]:
    """Validate PATCH body; returns normalized key→value for merge."""
    m = TenantAgentLLMPatch.model_validate(patch)
    return {k: v for k, v in m.model_dump(exclude_unset=True).items() if v is not None}


def tenant_agent_llm_public_fields(raw: dict[str, Any] | None) -> dict[str, Any]:
    """Shape stored ``tenant.settings`` into fields for ``TenantAgentLLMPublic``."""
    if not raw:
        return {
            "agent_llm_temperature": None,
            "agent_llm_model": None,
            "agent_max_conversation_history": None,
        }
    temp: float | None = None
    if AGENT_LLM_TEMPERATURE_KEY in raw and raw[AGENT_LLM_TEMPERATURE_KEY] is not None:
        try:
            temp = float(raw[AGENT_LLM_TEMPERATURE_KEY])
        except (TypeError, ValueError):
            temp = None
    model: str | None = None
    if raw.get(AGENT_LLM_MODEL_KEY):
        m = str(raw[AGENT_LLM_MODEL_KEY]).strip()[:128]
        model = m or None
    hist: int | None = None
    if AGENT_MAX_HISTORY_KEY in raw and raw[AGENT_MAX_HISTORY_KEY] is not None:
        try:
            hist = int(raw[AGENT_MAX_HISTORY_KEY])
        except (TypeError, ValueError):
            hist = None
    return {
        "agent_llm_temperature": temp,
        "agent_llm_model": model,
        "agent_max_conversation_history": hist,
    }
