"""Admin-only tenant settings and diagnostics."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select

from hospitai.api.deps import SessionDep, require_roles
from hospitai.api.schemas.admin_connector import TenantConnectorPublic, TenantConnectorUpdate
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
