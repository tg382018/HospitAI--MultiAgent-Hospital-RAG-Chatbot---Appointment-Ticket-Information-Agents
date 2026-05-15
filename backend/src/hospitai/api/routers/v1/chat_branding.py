"""Public chat branding + tenant logo asset routes."""

from __future__ import annotations

from fastapi import APIRouter, Query
from fastapi.responses import FileResponse
from sqlalchemy import select

from hospitai.api.deps import SessionDep
from hospitai.api.schemas.chat_branding import ChatBrandingPublic
from hospitai.infrastructure.db.models.tenant import Tenant
from hospitai.infrastructure.settings import get_settings
from hospitai.infrastructure.tenant_assets import (
    branding_public_response,
    resolve_favicon_path,
    resolve_logo_path,
)

router = APIRouter(tags=["public"])


async def _tenant_by_slug(session: SessionDep, slug: str) -> Tenant | None:
    stmt = select(Tenant).where(Tenant.slug == slug, Tenant.is_active.is_(True))
    return (await session.execute(stmt)).scalar_one_or_none()


@router.get("/public/chat-branding", response_model=ChatBrandingPublic)
async def public_chat_branding(
    session: SessionDep,
    slug: str | None = Query(default=None),
) -> ChatBrandingPublic:
    effective_slug = slug or get_settings().public_chat_default_tenant_slug
    tenant = await _tenant_by_slug(session, effective_slug)
    if tenant is None:
        from hospitai.application.tenant_branding import (
            DEFAULT_HEADER_BACKGROUND,
            DEFAULT_QUICK_ACTIONS,
            DEFAULT_WELCOME_SUBTITLE,
            DEFAULT_WELCOME_TITLE,
        )

        return ChatBrandingPublic(
            slug=effective_slug,
            header_background=DEFAULT_HEADER_BACKGROUND,
            welcome_title=DEFAULT_WELCOME_TITLE,
            welcome_subtitle=DEFAULT_WELCOME_SUBTITLE,
            logo_url=None,
            has_custom_logo=False,
            favicon_url=None,
            has_custom_favicon=False,
            quick_actions=DEFAULT_QUICK_ACTIONS,
        )
    return ChatBrandingPublic.model_validate(branding_public_response(tenant))


@router.get("/public/tenant-assets/{slug}/logo")
async def public_tenant_logo(
    session: SessionDep,
    slug: str,
) -> FileResponse:
    tenant = await _tenant_by_slug(session, slug)
    if tenant is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Tenant not found")
    path = resolve_logo_path(tenant)
    if path is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Logo not found")
    media = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }.get(path.suffix.lower(), "application/octet-stream")
    return FileResponse(path, media_type=media)


@router.get("/public/tenant-assets/{slug}/favicon")
async def public_tenant_favicon(
    session: SessionDep,
    slug: str,
) -> FileResponse:
    tenant = await _tenant_by_slug(session, slug)
    if tenant is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Tenant not found")
    path = resolve_favicon_path(tenant)
    if path is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Favicon not found")
    return FileResponse(path, media_type="image/x-icon")
