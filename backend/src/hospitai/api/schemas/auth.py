"""Pydantic models for auth endpoints."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from hospitai.infrastructure.db.models.enums import UserRole


class LoginRequest(BaseModel):
    tenant_slug: str = Field(..., min_length=1, max_length=64)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=256)


class RegisterRequest(BaseModel):
    tenant_slug: str = Field(..., min_length=1, max_length=64)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=256)
    full_name: str | None = Field(default=None, max_length=255)


class AdminRegisterRequest(BaseModel):
    tenant_slug: str = Field(..., min_length=1, max_length=64)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=256)
    key: str = Field(..., min_length=1, max_length=256)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(..., min_length=10)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(..., description="Access token lifetime in seconds")


class UserMeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str | None
    role: UserRole
    tenant_id: uuid.UUID
