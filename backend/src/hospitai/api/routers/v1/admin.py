"""Admin-only tenant settings and diagnostics."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select

from hospitai.api.deps import SessionDep, require_roles
from hospitai.api.http_mapping import raise_from_domain
from hospitai.api.schemas.admin_connector import (
    TenantConnectorProbeAccepted,
    TenantConnectorPublic,
    TenantConnectorUpdate,
)
from hospitai.api.schemas.admin_tenant import (
    AdminUserListResponse,
    AdminUserPatch,
    AdminUserPublic,
    TenantAgentLLMPublic,
    TenantPolicyPatch,
    TenantPolicyPublic,
)
from hospitai.application.errors import DomainError
from hospitai.application.tenant_admin import (
    admin_update_user,
    apply_agent_llm_settings_patch,
    get_tenant_for_admin,
    list_tenant_users,
    patch_tenant_policy,
)
from hospitai.application.tenant_agent_llm import (
    TenantAgentLLMPatch,
    tenant_agent_llm_public_fields,
)
from hospitai.application.tenant_policy import effective_policy
from hospitai.infrastructure.db.models.enums import UserRole
from hospitai.infrastructure.db.models.tenant import Tenant
from hospitai.infrastructure.db.models.user import User

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/ping")
async def admin_ping(
    _user: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
) -> dict[str, str]:
    return {"message": "ok", "scope": "admin"}


@router.get("/tenant-connector", response_model=TenantConnectorPublic)
async def get_tenant_connector(
    session: SessionDep,
    user: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
) -> TenantConnectorPublic:
    stmt = select(Tenant).where(Tenant.id == user.tenant_id)
    row = await session.execute(stmt)
    tenant = row.scalar_one_or_none()
    if tenant is None:
        return TenantConnectorPublic(
            external_hospital_base_url=None,
            has_external_hospital_api_key=False,
        )
    key = (tenant.external_hospital_api_key or "").strip()
    return TenantConnectorPublic(
        external_hospital_base_url=tenant.external_hospital_base_url,
        has_external_hospital_api_key=bool(key),
    )


@router.patch("/tenant-connector", response_model=TenantConnectorPublic)
async def patch_tenant_connector(
    session: SessionDep,
    current: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
    body: TenantConnectorUpdate,
) -> TenantConnectorPublic:
    stmt = select(Tenant).where(Tenant.id == current.tenant_id)
    row = await session.execute(stmt)
    tenant = row.scalar_one_or_none()
    if tenant is None:
        return TenantConnectorPublic(
            external_hospital_base_url=None,
            has_external_hospital_api_key=False,
        )
    patch = body.model_dump(exclude_unset=True)
    if "external_hospital_base_url" in patch:
        v = patch["external_hospital_base_url"]
        tenant.external_hospital_base_url = (v or "").strip() or None
    if "external_hospital_api_key" in patch:
        v = patch["external_hospital_api_key"]
        tenant.external_hospital_api_key = (v or "").strip() or None
    await session.commit()
    await session.refresh(tenant)
    key = (tenant.external_hospital_api_key or "").strip()
    return TenantConnectorPublic(
        external_hospital_base_url=tenant.external_hospital_base_url,
        has_external_hospital_api_key=bool(key),
    )


@router.post("/tenant-connector/probe", response_model=TenantConnectorProbeAccepted)
async def enqueue_external_connector_probe(
    user: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
) -> TenantConnectorProbeAccepted:
    """Dış HIS /v1/doctors erişimini Celery worker içinde dene (sohbeti bloklamaz)."""
    from hospitai.workers.tasks import probe_external_hospital_connectivity_task

    async_result = probe_external_hospital_connectivity_task.delay(str(user.tenant_id))
    return TenantConnectorProbeAccepted(task_id=async_result.id)


# ---- Tenant policy (JSONB flags) -------------------------------------------


@router.get("/tenant-policy", response_model=TenantPolicyPublic)
async def get_tenant_policy(
    session: SessionDep,
    user: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
) -> TenantPolicyPublic:
    tenant = await get_tenant_for_admin(session, tenant_id=user.tenant_id)
    pol = effective_policy(tenant)
    return TenantPolicyPublic(
        rag_retrieval_enabled=bool(pol.get("rag_retrieval_enabled", True)),
    )


@router.patch("/tenant-policy", response_model=TenantPolicyPublic)
async def patch_tenant_policy_endpoint(
    session: SessionDep,
    user: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
    body: TenantPolicyPatch,
) -> TenantPolicyPublic:
    tenant = await get_tenant_for_admin(session, tenant_id=user.tenant_id)
    patch = body.model_dump(exclude_unset=True)
    if not patch:
        pol = effective_policy(tenant)
        return TenantPolicyPublic(
            rag_retrieval_enabled=bool(pol.get("rag_retrieval_enabled", True)),
        )
    try:
        await patch_tenant_policy(session, tenant=tenant, policy_patch=patch)
        await session.commit()
        await session.refresh(tenant)
    except DomainError as e:
        await session.rollback()
        raise_from_domain(e)
    pol = effective_policy(tenant)
    return TenantPolicyPublic(
        rag_retrieval_enabled=bool(pol.get("rag_retrieval_enabled", True)),
    )


# ---- Tenant agent LLM (JSONB overrides) ------------------------------------


@router.get("/tenant-agent-llm", response_model=TenantAgentLLMPublic)
async def get_tenant_agent_llm(
    session: SessionDep,
    user: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
) -> TenantAgentLLMPublic:
    tenant = await get_tenant_for_admin(session, tenant_id=user.tenant_id)
    raw = tenant.settings if isinstance(tenant.settings, dict) else None
    return TenantAgentLLMPublic.model_validate(tenant_agent_llm_public_fields(raw))


@router.patch("/tenant-agent-llm", response_model=TenantAgentLLMPublic)
async def patch_tenant_agent_llm(
    session: SessionDep,
    user: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
    body: TenantAgentLLMPatch,
) -> TenantAgentLLMPublic:
    tenant = await get_tenant_for_admin(session, tenant_id=user.tenant_id)
    patch = body.model_dump(exclude_unset=True)
    if not patch:
        raw = tenant.settings if isinstance(tenant.settings, dict) else None
        return TenantAgentLLMPublic.model_validate(tenant_agent_llm_public_fields(raw))
    try:
        await apply_agent_llm_settings_patch(session, tenant=tenant, patch=patch)
        await session.commit()
        await session.refresh(tenant)
    except DomainError as e:
        await session.rollback()
        raise_from_domain(e)
    raw = tenant.settings if isinstance(tenant.settings, dict) else None
    return TenantAgentLLMPublic.model_validate(tenant_agent_llm_public_fields(raw))


# ---- Tenant users ----------------------------------------------------------


@router.get("/users", response_model=AdminUserListResponse)
async def list_admin_users(
    session: SessionDep,
    user: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
) -> AdminUserListResponse:
    rows = await list_tenant_users(session, tenant_id=user.tenant_id)
    return AdminUserListResponse(users=[AdminUserPublic.model_validate(u) for u in rows])


@router.patch("/users/{user_id}", response_model=AdminUserPublic)
async def patch_admin_user(
    session: SessionDep,
    user: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
    user_id: uuid.UUID,
    body: AdminUserPatch,
) -> AdminUserPublic:
    patch = body.model_dump(exclude_unset=True)
    if not patch:
        stmt = select(User).where(User.id == user_id, User.tenant_id == user.tenant_id)
        row = await session.execute(stmt)
        u = row.scalar_one_or_none()
        if u is None:
            raise_from_domain(DomainError("user_not_found", "User not found", status_code=404))
        return AdminUserPublic.model_validate(u)
    try:
        updated = await admin_update_user(
            session,
            tenant_id=user.tenant_id,
            actor=user,
            target_user_id=user_id,
            full_name=patch.get("full_name") if "full_name" in patch else None,
            role=patch.get("role") if "role" in patch else None,
            is_active=patch.get("is_active") if "is_active" in patch else None,
        )
        await session.commit()
        await session.refresh(updated)
    except DomainError as e:
        await session.rollback()
        raise_from_domain(e)
    return AdminUserPublic.model_validate(updated)
