"""Application settings (env-driven)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_BACKEND_ROOT / ".env",
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
    admin_registration_key: str | None = Field(
        default=None,
        validation_alias="ADMIN_REGISTRATION_KEY",
        description=(
            "Shared secret required for POST /auth/register-admin. "
            "Unset disables admin self-registration."
        ),
    )
    public_chat_default_tenant_slug: str = Field(
        default="demo-hospital",
        validation_alias="PUBLIC_CHAT_DEFAULT_TENANT_SLUG",
        description="Tenant slug when chat is used without JWT and X-Tenant-Slug is omitted.",
    )
    hospital_bridge_http_base_url: str | None = Field(
        default=None,
        validation_alias="HOSPITAL_BRIDGE_HTTP_BASE_URL",
        description=(
            "Tüm tenantlar için varsayılan hastane köprü HTTP tabanı (tenant dış URL yoksa). "
            "POST {base}/v1/hospitai-bridge/…"
        ),
    )
    hospital_bridge_rabbitmq_url: str | None = Field(
        default=None,
        validation_alias="HOSPITAL_BRIDGE_RABBITMQ_URL",
        description=(
            "Hastane köprüsü için RabbitMQ broker URL (amqp://…). HTTP tabanı yokken yayın kullanılır."
        ),
    )

    openai_api_key: str = Field(
        default="",
        validation_alias="OPENAI_API_KEY",
        description="Single key used to fill empty LLM_API_KEY and/or EMBEDDING_API_KEY.",
    )

    langchain_api_key: str = Field(
        default="",
        validation_alias="LANGCHAIN_API_KEY",
        description="LangSmith / LangChain observability (exported to os.environ at startup).",
    )
    langchain_tracing_v2: bool = Field(
        default=False,
        validation_alias="LANGCHAIN_TRACING_V2",
        description="When true, sets LANGCHAIN_TRACING_V2=true for LangSmith tracing.",
    )
    langchain_project: str = Field(
        default="",
        validation_alias="LANGCHAIN_PROJECT",
        description="Optional LangSmith project name.",
    )
    tavily_api_key: str = Field(
        default="",
        validation_alias="TAVILY_API_KEY",
        description="Tavily web search API key (exported to os.environ; use when tools need it).",
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
        description="OpenAI API key for embeddings; optional if OPENAI_API_KEY is set.",
    )
    embedding_dimensions: int = Field(
        default=1536,
        validation_alias="EMBEDDING_DIMENSIONS",
    )

    # ---- LLM ----
    llm_model: str = Field(
        default="gpt-4o",
        validation_alias="LLM_MODEL",
        description="Default LLM model for the chat workflow.",
    )
    llm_api_key: str = Field(
        default="",
        validation_alias="LLM_API_KEY",
        description="OpenAI API key for LLM calls; optional if OPENAI_API_KEY is set.",
    )
    llm_base_url: str | None = Field(
        default=None,
        validation_alias="LLM_BASE_URL",
        description="Optional OpenAI-compatible base URL for LLM calls.",
    )
    llm_temperature: float = Field(
        default=0.25,
        validation_alias="LLM_TEMPERATURE",
        description="Temperature for LLM responses.",
    )
    max_conversation_history: int = Field(
        default=20,
        validation_alias="MAX_CONVERSATION_HISTORY",
        description="Max number of recent messages to include in context.",
    )

    # ---- Chat rate & length limits ----
    chat_max_messages_per_conversation: int = Field(
        default=100,
        validation_alias="CHAT_MAX_MESSAGES_PER_CONVERSATION",
        description=(
            "Hard limit on total messages (user + assistant) per conversation. "
            "Prevents users from abusing AI limits in a single session."
        ),
    )
    chat_rate_limit: str = Field(
        default="60/minute",
        validation_alias="CHAT_RATE_LIMIT",
        description=(
            "SlowAPI rate limit string per IP for chat endpoints "
            "(e.g. '30/minute', '200/hour'). "
            "Industry standard: ~1 msg/s for interactive chat."
        ),
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

    # ---- Database connection pool ----
    db_pool_size: int = Field(
        default=10,
        validation_alias="DB_POOL_SIZE",
        description="SQLAlchemy async engine pool_size (concurrent connections held open).",
    )
    db_max_overflow: int = Field(
        default=20,
        validation_alias="DB_MAX_OVERFLOW",
        description="Extra connections allowed above pool_size before blocking.",
    )
    db_pool_timeout: int = Field(
        default=30,
        validation_alias="DB_POOL_TIMEOUT",
        description="Seconds to wait for a connection from the pool before raising TimeoutError.",
    )
    db_pool_recycle: int = Field(
        default=1800,
        validation_alias="DB_POOL_RECYCLE",
        description="Seconds after which a connection is recycled (avoids stale connections).",
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
    tenant_assets_dir: str = Field(
        default="data/tenant-assets",
        validation_alias="TENANT_ASSETS_DIR",
        description="Directory for per-tenant uploaded chat logos (relative to backend/).",
    )

    def cors_origin_list(self) -> list[str]:
        return [p.strip() for p in self.cors_origins.split(",") if p.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
