"""Application settings (env-driven)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_BACKEND_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = Field(
        default="postgresql+asyncpg://hospitai:hospitai_dev_password@127.0.0.1:5432/hospitai",
        validation_alias="DATABASE_URL",
    )
    environment: str = Field(default="development", validation_alias="ENVIRONMENT")
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")
    cors_origins: str = Field(
        default="http://127.0.0.1:5173,http://localhost:5173",
        validation_alias="CORS_ORIGINS",
    )
    jwt_secret: str = Field(
        default="dev-only-change-me-min-16-chars-please-use-openssl",
        validation_alias="JWT_SECRET",
        min_length=16,
    )
    jwt_algorithm: str = Field(default="HS256", validation_alias="JWT_ALGORITHM")
    access_token_expire_minutes: int = Field(
        default=30,
        validation_alias="ACCESS_TOKEN_EXPIRE_MINUTES",
    )
    refresh_token_expire_days: int = Field(
        default=7,
        validation_alias="REFRESH_TOKEN_EXPIRE_DAYS",
    )
    internal_api_key: str | None = Field(default=None, validation_alias="INTERNAL_API_KEY")
    allow_open_registration: bool = Field(
        default=True,
        validation_alias="ALLOW_OPEN_REGISTRATION",
        description="If false, only existing admins can create users (future).",
    )

    # ---- RAG / Vector DB ----
    chroma_host: str = Field(
        default="localhost",
        validation_alias="CHROMA_HOST",
    )
    chroma_port: int = Field(
        default=8001,
        validation_alias="CHROMA_PORT",
    )
    chroma_collection_prefix: str = Field(
        default="hospitai",
        validation_alias="CHROMA_COLLECTION_PREFIX",
    )

    # ---- Embeddings ----
    embedding_model: str = Field(
        default="text-embedding-3-small",
        validation_alias="EMBEDDING_MODEL",
    )
    embedding_api_key: str = Field(
        default="",
        validation_alias="EMBEDDING_API_KEY",
        description="OpenAI API key for embeddings (falls back to OPENAI_API_KEY env).",
    )
    embedding_dimensions: int = Field(
        default=1536,
        validation_alias="EMBEDDING_DIMENSIONS",
    )

    # ---- LLM ----
    llm_model: str = Field(
        default="gpt-4o-mini",
        validation_alias="LLM_MODEL",
        description="Default LLM model for the chat workflow.",
    )
    llm_api_key: str = Field(
        default="",
        validation_alias="LLM_API_KEY",
        description="OpenAI API key for LLM calls (falls back to OPENAI_API_KEY env).",
    )
    llm_base_url: str | None = Field(
        default=None,
        validation_alias="LLM_BASE_URL",
        description="Optional OpenAI-compatible base URL for LLM calls.",
    )
    llm_temperature: float = Field(
        default=0.0,
        validation_alias="LLM_TEMPERATURE",
        description="Temperature for LLM responses.",
    )
    max_conversation_history: int = Field(
        default=20,
        validation_alias="MAX_CONVERSATION_HISTORY",
        description="Max number of recent messages to include in context.",
    )

    # ---- Chunking ----
    chunk_size: int = Field(
        default=500,
        validation_alias="CHUNK_SIZE",
        description="Max tokens per chunk for document ingestion.",
    )
    chunk_overlap: int = Field(
        default=50,
        validation_alias="CHUNK_OVERLAP",
        description="Token overlap between consecutive chunks.",
    )

    # ---- Celery (background workers) ----
    celery_broker_url: str = Field(
        default="redis://127.0.0.1:6379/0",
        validation_alias="CELERY_BROKER_URL",
    )
    celery_result_backend: str | None = Field(
        default=None,
        validation_alias="CELERY_RESULT_BACKEND",
        description="Defaults to CELERY_BROKER_URL when unset.",
    )

    def cors_origin_list(self) -> list[str]:
        return [p.strip() for p in self.cors_origins.split(",") if p.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
