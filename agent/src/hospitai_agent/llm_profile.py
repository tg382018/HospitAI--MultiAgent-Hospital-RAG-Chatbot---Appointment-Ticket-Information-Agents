"""LLM configuration injected by the platform backend at startup."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from hospitai_agent.settings import get_agent_settings


@dataclass(frozen=True, slots=True)
class LLMProfile:
    llm_model: str
    llm_api_key: str
    llm_base_url: str | None
    llm_temperature: float
    embedding_api_key: str


_profile: LLMProfile | None = None


def configure_llm_profile(profile: LLMProfile) -> None:
    """Called once from FastAPI lifespan with platform `Settings`."""
    global _profile
    _profile = profile
    from hospitai_agent.llm_client import clear_llm_cache

    clear_llm_cache()


def get_llm_profile() -> LLMProfile:
    if _profile is not None:
        return _profile
    s = get_agent_settings()
    return LLMProfile(
        llm_model=s.llm_model,
        llm_api_key=s.llm_api_key,
        llm_base_url=s.llm_base_url,
        llm_temperature=s.llm_temperature,
        embedding_api_key=s.embedding_api_key,
    )


def merge_llm_profile(base: LLMProfile, overrides: dict[str, Any] | None) -> LLMProfile:
    """Apply safe per-tenant overrides (model, temperature). API keys stay from ``base``."""
    if not overrides:
        return base
    kwargs: dict[str, Any] = {}
    if "llm_temperature" in overrides:
        try:
            t = float(overrides["llm_temperature"])
            kwargs["llm_temperature"] = max(0.0, min(2.0, t))
        except (TypeError, ValueError):
            pass
    if overrides.get("llm_model"):
        m = str(overrides["llm_model"]).strip()[:128]
        if m:
            kwargs["llm_model"] = m
    if not kwargs:
        return base
    return replace(base, **kwargs)
