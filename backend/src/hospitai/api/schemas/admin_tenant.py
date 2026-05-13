"""Admin tenant policy and user list schemas."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field

from hospitai.infrastructure.db.models.enums import UserRole


class TenantPolicyPublic(BaseModel):
    """Known tenant policy flags (subset of ``tenants.settings``)."""

    rag_retrieval_enabled: bool = Field(
        ...,
        description="When false, authenticated RAG /retrieve is disabled for this tenant.",
    )


class TenantPolicyPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rag_retrieval_enabled: bool | None = None


class TenantAgentLLMPublic(BaseModel):
    """Per-tenant agent LLM overrides (subset of ``tenants.settings``)."""

    agent_llm_temperature: float | None = Field(
        default=None,
        description="Override LLM temperature; omit or null uses platform default.",
    )
    agent_llm_model: str | None = Field(
        default=None,
        description="Override chat model id; omit or null uses platform default.",
    )
    agent_max_conversation_history: int | None = Field(
        default=None,
        description="Max prior messages loaded into context (1–50); null uses platform default.",
    )


class AdminUserPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str | None
    role: UserRole
    is_active: bool


class AdminUserListResponse(BaseModel):
    users: list[AdminUserPublic]


class AdminUserPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str | None = None
    role: UserRole | None = None
    is_active: bool | None = None
