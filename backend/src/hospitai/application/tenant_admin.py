"""Admin operations: tenant users and policy JSONB."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from hospitai.application.errors import DomainError
from hospitai.application.tenant_agent_llm import (
    merge_agent_llm_settings,
    validate_agent_llm_patch,
)
from hospitai.application.tenant_policy import merge_policy_patch
from hospitai.infrastructure.db.models.enums import UserRole
from hospitai.infrastructure.db.models.tenant import Tenant
from hospitai.infrastructure.db.models.user import User


async def list_tenant_users(session: AsyncSession, *, tenant_id: uuid.UUID) -> list[User]:
    stmt = select(User).where(User.tenant_id == tenant_id).order_by(User.email.asc())
    res = await session.execute(stmt)
    return list(res.scalars().all())


async def count_active_admins(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    exclude_user_id: uuid.UUID | None = None,
) -> int:
    stmt = (
        select(func.count())
        .select_from(User)
        .where(
            User.tenant_id == tenant_id,
            User.role == UserRole.ADMIN,
            User.is_active.is_(True),
        )
    )
    if exclude_user_id is not None:
        stmt = stmt.where(User.id != exclude_user_id)
    return int((await session.execute(stmt)).scalar_one())


async def admin_update_user(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    actor: User,
    target_user_id: uuid.UUID,
    full_name: str | None = None,
    role: UserRole | None = None,
    is_active: bool | None = None,
) -> User:
    stmt = select(User).where(User.id == target_user_id, User.tenant_id == tenant_id)
    target = (await session.execute(stmt)).scalar_one_or_none()
    if target is None:
        raise DomainError("user_not_found", "User not found", status_code=404)

    if target.id == actor.id:
        if is_active is False:
            raise DomainError(
                "invalid_operation",
                "You cannot deactivate yourself",
                status_code=409,
            )
        if role is not None and role != actor.role:
            raise DomainError(
                "invalid_operation",
                "You cannot change your own role; use another admin account",
                status_code=409,
            )

    if (
        role is not None
        and target.role == UserRole.ADMIN
        and role != UserRole.ADMIN
        and await count_active_admins(session, tenant_id=tenant_id, exclude_user_id=target.id) == 0
    ):
        raise DomainError(
            "last_admin",
            "Cannot remove the last active admin for this tenant",
            status_code=409,
        )

    if (
        is_active is False
        and target.role == UserRole.ADMIN
        and await count_active_admins(session, tenant_id=tenant_id, exclude_user_id=target.id) == 0
    ):
        raise DomainError(
            "last_admin",
            "Cannot deactivate the last active admin for this tenant",
            status_code=409,
        )

    if full_name is not None:
        target.full_name = full_name.strip() or None
    if role is not None:
        target.role = role
    if is_active is not None:
        target.is_active = is_active

    await session.flush()
    return target


async def get_tenant_for_admin(session: AsyncSession, *, tenant_id: uuid.UUID) -> Tenant:
    stmt = select(Tenant).where(Tenant.id == tenant_id)
    row = await session.execute(stmt)
    tenant = row.scalar_one_or_none()
    if tenant is None:
        raise DomainError("tenant_not_found", "Tenant not found", status_code=404)
    return tenant


async def patch_tenant_policy(
    session: AsyncSession,
    *,
    tenant: Tenant,
    policy_patch: dict[str, object],
) -> Tenant:
    merged = merge_policy_patch(tenant.settings, policy_patch)
    tenant.settings = merged
    await session.flush()
    return tenant


async def apply_agent_llm_settings_patch(
    session: AsyncSession,
    *,
    tenant: Tenant,
    patch: dict[str, Any],
) -> Tenant:
    validated = validate_agent_llm_patch(patch)
    merged = merge_agent_llm_settings(
        tenant.settings if isinstance(tenant.settings, dict) else None,
        validated,
    )
    tenant.settings = merged
    await session.flush()
    return tenant
