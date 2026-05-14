"""Agent-side settings (LLM / intent). Uses the same env vars as platform backend."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AgentSettings(BaseSettings):
    """Subset of platform settings needed by the LangGraph workflow."""

    model_config = SettingsConfigDict(
        env_file=(".env",),
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    @model_validator(mode="before")
    @classmethod
    def _merge_openai_unified_key(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        merged = dict(data)

        def pick_str(*keys: str) -> str:
            for k in keys:
                v = merged.get(k)
                if v is not None and str(v).strip():
                    return str(v).strip()
            return ""

        fb = pick_str("openai_api_key", "OPENAI_API_KEY")
        if not fb:
            return merged

        if not pick_str("llm_api_key", "LLM_API_KEY"):
            merged["llm_api_key"] = fb
        if not pick_str("embedding_api_key", "EMBEDDING_API_KEY"):
            merged["embedding_api_key"] = fb
        return merged

    llm_model: str = Field(default="gpt-4o", validation_alias="LLM_MODEL")
    llm_api_key: str = Field(default="", validation_alias="LLM_API_KEY")
    llm_base_url: str | None = Field(default=None, validation_alias="LLM_BASE_URL")
    llm_temperature: float = Field(default=0.25, validation_alias="LLM_TEMPERATURE")
    embedding_api_key: str = Field(default="", validation_alias="EMBEDDING_API_KEY")
    openai_api_key: str = Field(
        default="",
        validation_alias="OPENAI_API_KEY",
        description="Fills empty LLM_API_KEY and/or EMBEDDING_API_KEY when set.",
    )


@lru_cache
def get_agent_settings() -> AgentSettings:
    return AgentSettings()
