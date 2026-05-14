"""API v1 smoke routes + public tenant info."""

from __future__ import annotations

from fastapi import APIRouter, Query

from hospitai import __version__
from hospitai.api.deps import SessionDep
from hospitai.infrastructure.settings import get_settings

router = APIRouter(tags=["v1"])


@router.get("/ping")
async def ping() -> dict[str, str]:
    return {"message": "pong", "api_version": "v1", "service_version": __version__}


@router.get("/public/tenant-info")
async def public_tenant_info(
    session: SessionDep,
    slug: str | None = Query(default=None),
) -> dict[str, str]:
    """Return public display info for a tenant (no auth required).

    Used by chat & other frontends to show the hospital name dynamically.
    Falls back to the default tenant slug from settings.
    """
    from sqlalchemy import select

    from hospitai.infrastructure.db.models.tenant import Tenant

    effective_slug = slug or get_settings().public_chat_default_tenant_slug
    stmt = select(Tenant.name, Tenant.slug).where(Tenant.slug == effective_slug)
    row = (await session.execute(stmt)).first()
    if row is None:
        return {"name": effective_slug, "slug": effective_slug}
    return {"name": row.name, "slug": row.slug}
