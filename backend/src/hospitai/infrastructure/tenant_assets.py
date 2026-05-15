"""Local filesystem storage for per-tenant chat assets (logos)."""

from __future__ import annotations

import uuid
from pathlib import Path

from hospitai.application.tenant_branding import CHAT_FAVICON_FILE_KEY, CHAT_LOGO_FILE_KEY
from hospitai.infrastructure.db.models.tenant import Tenant
from hospitai.infrastructure.settings import Settings, get_settings

MAX_LOGO_BYTES = 2 * 1024 * 1024
ALLOWED_LOGO_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".webp"})
ALLOWED_LOGO_MIME = frozenset(
    {"image/png", "image/jpeg", "image/jpg", "image/webp"}
)

_EXT_BY_MIME: dict[str, str] = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/webp": ".webp",
}


def tenant_assets_root(settings: Settings | None = None) -> Path:
    s = settings or get_settings()
    root = Path(s.tenant_assets_dir)
    if not root.is_absolute():
        root = Path(__file__).resolve().parents[3] / root
    return root


def tenant_asset_dir(tenant_id: uuid.UUID, settings: Settings | None = None) -> Path:
    return tenant_assets_root(settings) / str(tenant_id)


def resolve_logo_path(tenant: Tenant, settings: Settings | None = None) -> Path | None:
    branding = tenant.branding if isinstance(tenant.branding, dict) else None
    if not branding:
        return None
    filename = branding.get(CHAT_LOGO_FILE_KEY)
    if not filename or not isinstance(filename, str):
        return None
    path = tenant_asset_dir(tenant.id, settings) / filename
    return path if path.is_file() else None


def public_logo_url(tenant: Tenant) -> str | None:
    if resolve_logo_path(tenant) is None:
        return None
    v = ""
    if tenant.updated_at is not None:
        v = str(int(tenant.updated_at.timestamp()))
    return f"/api/v1/public/tenant-assets/{tenant.slug}/logo?v={v}"


def validate_logo_upload(
    *,
    filename: str | None,
    content_type: str | None,
    size: int,
) -> str:
    if size <= 0 or size > MAX_LOGO_BYTES:
        raise ValueError(f"Logo must be at most {MAX_LOGO_BYTES // (1024 * 1024)} MB")
    ext = ""
    if filename:
        ext = Path(filename).suffix.lower()
    mime = (content_type or "").split(";")[0].strip().lower()
    if ext in ALLOWED_LOGO_EXTENSIONS:
        return ext
    if mime in ALLOWED_LOGO_MIME:
        return _EXT_BY_MIME.get(mime, ".png")
    raise ValueError("Logo must be PNG, JPEG, or WebP (max 2 MB)")


def save_tenant_logo(
    tenant: Tenant,
    *,
    data: bytes,
    ext: str,
    settings: Settings | None = None,
) -> str:
    if ext not in ALLOWED_LOGO_EXTENSIONS:
        raise ValueError("Unsupported logo extension")
    dest_dir = tenant_asset_dir(tenant.id, settings)
    dest_dir.mkdir(parents=True, exist_ok=True)
    for old in dest_dir.glob("logo.*"):
        old.unlink(missing_ok=True)
    filename = f"logo{ext}"
    (dest_dir / filename).write_bytes(data)
    return filename


def delete_tenant_logo(tenant: Tenant, settings: Settings | None = None) -> None:
    dest_dir = tenant_asset_dir(tenant.id, settings)
    if dest_dir.is_dir():
        for old in dest_dir.glob("logo.*"):
            old.unlink(missing_ok=True)


MAX_FAVICON_BYTES = 256 * 1024
_FAVICON_MAGIC = b"\x00\x00\x01\x00"
_ALLOWED_FAVICON_MIME = frozenset(
    {
        "image/x-icon",
        "image/vnd.microsoft.icon",
        "application/octet-stream",
    }
)


def resolve_favicon_path(tenant: Tenant, settings: Settings | None = None) -> Path | None:
    branding = tenant.branding if isinstance(tenant.branding, dict) else None
    if not branding:
        return None
    filename = branding.get(CHAT_FAVICON_FILE_KEY)
    if not filename or not isinstance(filename, str):
        return None
    path = tenant_asset_dir(tenant.id, settings) / filename
    return path if path.is_file() else None


def public_favicon_url(tenant: Tenant) -> str | None:
    if resolve_favicon_path(tenant) is None:
        return None
    v = ""
    if tenant.updated_at is not None:
        v = str(int(tenant.updated_at.timestamp()))
    return f"/api/v1/public/tenant-assets/{tenant.slug}/favicon?v={v}"


def _is_valid_ico_payload(data: bytes) -> bool:
    if len(data) < 6:
        return False
    return data[:4] == _FAVICON_MAGIC


def validate_favicon_upload(
    *,
    filename: str | None,
    content_type: str | None,
    size: int,
    data: bytes,
) -> None:
    if size <= 0 or size > MAX_FAVICON_BYTES:
        raise ValueError(f"Favicon must be at most {MAX_FAVICON_BYTES // 1024} KB")
    ext = Path(filename or "").suffix.lower()
    if ext and ext != ".ico":
        raise ValueError("Favicon must be a .ico file")
    mime = (content_type or "").split(";")[0].strip().lower()
    if mime and mime not in _ALLOWED_FAVICON_MIME:
        raise ValueError("Favicon must be a .ico file")
    if not _is_valid_ico_payload(data):
        raise ValueError("Invalid ICO file format")


def save_tenant_favicon(
    tenant: Tenant,
    *,
    data: bytes,
    settings: Settings | None = None,
) -> str:
    validate_favicon_upload(filename="favicon.ico", content_type="image/x-icon", size=len(data), data=data)
    dest_dir = tenant_asset_dir(tenant.id, settings)
    dest_dir.mkdir(parents=True, exist_ok=True)
    for old in dest_dir.glob("favicon.*"):
        old.unlink(missing_ok=True)
    filename = "favicon.ico"
    (dest_dir / filename).write_bytes(data)
    return filename


def delete_tenant_favicon(tenant: Tenant, settings: Settings | None = None) -> None:
    dest_dir = tenant_asset_dir(tenant.id, settings)
    if dest_dir.is_dir():
        for old in dest_dir.glob("favicon.*"):
            old.unlink(missing_ok=True)


def branding_public_response(tenant: Tenant) -> dict[str, object]:
    from hospitai.application.tenant_branding import branding_public_fields

    return branding_public_fields(
        tenant,
        logo_url=public_logo_url(tenant),
        favicon_url=public_favicon_url(tenant),
    )
