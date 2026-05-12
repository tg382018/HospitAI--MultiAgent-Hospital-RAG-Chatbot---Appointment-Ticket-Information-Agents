"""Authentication use-cases (tenant-scoped login / register)."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import select

from hospitai.infrastructure.db.models.enums import UserRole
from hospitai.infrastructure.db.models.tenant import Tenant
from hospitai.infrastructure.db.models.user import User
from hospitai.infrastructure.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from hospitai.infrastructure.settings import Settings


class AuthError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


async def get_tenant_by_slug(session: AsyncSession, slug: str) -> Tenant:
    stmt = select(Tenant).where(Tenant.slug == slug, Tenant.is_active.is_(True))
    result = await session.execute(stmt)
    tenant = result.scalar_one_or_none()
    if tenant is None:
        raise AuthError("tenant_not_found", "Unknown or inactive hospital slug", 404)
    return tenant


async def authenticate_user(
    session: AsyncSession,
    *,
    tenant_slug: str,
    email: str,
    password: str,
) -> User:
    tenant = await get_tenant_by_slug(session, tenant_slug)
    stmt = select(User).where(
        User.tenant_id == tenant.id,
        User.email == email.strip().lower(),
        User.is_active.is_(True),
    )
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()
    if user is None or not verify_password(password, user.password_hash or ""):
        raise AuthError("invalid_credentials", "Incorrect email or password", 401)
    return user


async def register_patient(
    session: AsyncSession,
    settings: Settings,
    *,
    tenant_slug: str,
    email: str,
    password: str,
    full_name: str | None,
) -> User:
    if not settings.allow_open_registration:
        raise AuthError("registration_closed", "Open registration is disabled", 403)

    tenant = await get_tenant_by_slug(session, tenant_slug)
    normalized = email.strip().lower()
    existing = await session.execute(
        select(User.id).where(User.tenant_id == tenant.id, User.email == normalized)
    )
    if existing.scalar_one_or_none() is not None:
        raise AuthError("email_taken", "Email already registered for this hospital", 409)

    user = User(
        tenant_id=tenant.id,
        email=normalized,
        password_hash=hash_password(password),
        full_name=full_name.strip() if full_name else None,
        role=UserRole.PATIENT,
        is_active=True,
    )
    session.add(user)
    await session.flush()
    await session.refresh(user)
    return user


def issue_token_pair(user: User, settings: Settings) -> tuple[str, str]:
    access = create_access_token(
        user_id=user.id,
        tenant_id=user.tenant_id,
        role=user.role.value,
        email=user.email,
        settings=settings,
    )
    refresh = create_refresh_token(
        user_id=user.id,
        tenant_id=user.tenant_id,
        settings=settings,
    )
    return access, refresh


async def get_user_for_claims(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    tenant_id: uuid.UUID,
) -> User | None:
    stmt = select(User).where(
        User.id == user_id,
        User.tenant_id == tenant_id,
        User.is_active.is_(True),
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()
