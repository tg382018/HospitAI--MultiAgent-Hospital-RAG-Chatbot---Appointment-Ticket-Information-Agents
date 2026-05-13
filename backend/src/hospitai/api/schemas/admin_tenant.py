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
