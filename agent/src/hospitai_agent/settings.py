"""Agent-side settings (LLM / intent). Uses the same env vars as platform backend."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AgentSettings(BaseSettings):
    """Subset of platform settings needed by the LangGraph workflow."""

    model_config = SettingsConfigDict(
        env_file=(".env",),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    llm_model: str = Field(default="gpt-4o-mini", validation_alias="LLM_MODEL")
    llm_api_key: str = Field(default="", validation_alias="LLM_API_KEY")
    llm_base_url: str | None = Field(default=None, validation_alias="LLM_BASE_URL")
    llm_temperature: float = Field(default=0.0, validation_alias="LLM_TEMPERATURE")
    embedding_api_key: str = Field(default="", validation_alias="EMBEDDING_API_KEY")


@lru_cache
def get_agent_settings() -> AgentSettings:
    return AgentSettings()
