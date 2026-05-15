"""Tenant chat UI branding stored in ``Tenant.branding`` JSONB."""

from __future__ import annotations

import re
from typing import Any, Protocol

CHAT_HEADER_BACKGROUND_KEY = "chat_header_background"
CHAT_WELCOME_TITLE_KEY = "chat_welcome_title"
CHAT_WELCOME_SUBTITLE_KEY = "chat_welcome_subtitle"
CHAT_LOGO_FILE_KEY = "chat_logo_file"
CHAT_FAVICON_FILE_KEY = "chat_favicon_file"
CHAT_QUICK_ACTIONS_KEY = "chat_quick_actions"

DEFAULT_HEADER_BACKGROUND = (
    "linear-gradient(135deg, #0ea5e9 0%, #0891b2 50%, #14b8a6 100%)"
)
DEFAULT_WELCOME_TITLE = "Merhaba! 👋"
DEFAULT_WELCOME_SUBTITLE = (
    "Size nasıl yardımcı olabilirim? Randevu almak, randevularınızı sorgulamak "
    "veya bir şikayetinizi iletmek için aşağıdan başlayabilirsiniz."
)
DEFAULT_QUICK_ACTIONS: list[dict[str, str]] = [
    {"icon": "📅", "label": "Randevu Al"},
    {"icon": "📋", "label": "Randevularım"},
    {"icon": "💬", "label": "Şikayet Bildir"},
    {"icon": "❓", "label": "Hastane Bilgisi"},
]

_BRANDING_KEYS = frozenset(
    {
        CHAT_HEADER_BACKGROUND_KEY,
        CHAT_WELCOME_TITLE_KEY,
        CHAT_WELCOME_SUBTITLE_KEY,
        CHAT_LOGO_FILE_KEY,
        CHAT_FAVICON_FILE_KEY,
        CHAT_QUICK_ACTIONS_KEY,
    }
)

_MAX_QUICK_ACTIONS = 8

_UNSAFE_CSS = re.compile(r"[;<>]|url\s*\(", re.IGNORECASE)


class _TenantBrandingSource(Protocol):
    branding: dict[str, Any] | None
    slug: str
    updated_at: object | None


def default_branding() -> dict[str, Any]:
    return {
        CHAT_HEADER_BACKGROUND_KEY: DEFAULT_HEADER_BACKGROUND,
        CHAT_WELCOME_TITLE_KEY: DEFAULT_WELCOME_TITLE,
        CHAT_WELCOME_SUBTITLE_KEY: DEFAULT_WELCOME_SUBTITLE,
        CHAT_LOGO_FILE_KEY: None,
        CHAT_FAVICON_FILE_KEY: None,
        CHAT_QUICK_ACTIONS_KEY: list(DEFAULT_QUICK_ACTIONS),
    }


def validate_header_background(value: str) -> str:
    v = value.strip()
    if not v or len(v) > 512:
        raise ValueError("header_background must be 1–512 characters")
    if _UNSAFE_CSS.search(v):
        raise ValueError("header_background contains disallowed characters")
    return v


def validate_welcome_text(value: str, *, field: str, max_len: int = 500) -> str:
    v = value.strip()
    if not v:
        raise ValueError(f"{field} must not be empty")
    if len(v) > max_len:
        raise ValueError(f"{field} must be at most {max_len} characters")
    return v


def validate_quick_actions(value: object) -> list[dict[str, str]]:
    if not isinstance(value, list):
        raise ValueError("quick_actions must be a list")
    if not value or len(value) > _MAX_QUICK_ACTIONS:
        raise ValueError(f"quick_actions must have 1–{_MAX_QUICK_ACTIONS} items")
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for i, item in enumerate(value):
        if not isinstance(item, dict):
            raise ValueError(f"quick_actions[{i}] must be an object")
        icon = str(item.get("icon", "")).strip()
        label = str(item.get("label", "")).strip()
        if not label or len(label) > 80:
            raise ValueError(f"quick_actions[{i}].label must be 1–80 characters")
        if len(icon) > 8:
            raise ValueError(f"quick_actions[{i}].icon must be at most 8 characters")
        key = label.casefold()
        if key in seen:
            raise ValueError("quick_actions labels must be unique")
        seen.add(key)
        out.append({"icon": icon, "label": label})
    return out


def effective_branding(tenant: _TenantBrandingSource | None) -> dict[str, Any]:
    base = default_branding()
    raw = tenant.branding if tenant and isinstance(tenant.branding, dict) else None
    if not raw:
        return dict(base)
    out = dict(base)
    for k in _BRANDING_KEYS:
        if k not in raw or raw[k] is None:
            continue
        if k == CHAT_QUICK_ACTIONS_KEY:
            try:
                out[k] = validate_quick_actions(raw[k])
            except ValueError:
                pass
        else:
            out[k] = raw[k]
    return out


def merge_branding_patch(
    current: dict[str, Any] | None, patch: dict[str, Any]
) -> dict[str, Any]:
    defaults = default_branding()
    out: dict[str, Any] = dict(current) if isinstance(current, dict) else {}
    for k, v in defaults.items():
        out.setdefault(k, v)
    for k, v in patch.items():
        if k in _BRANDING_KEYS:
            out[k] = v
    return out


def branding_public_fields(
    tenant: _TenantBrandingSource,
    *,
    logo_url: str | None,
    favicon_url: str | None = None,
) -> dict[str, Any]:
    b = effective_branding(tenant)
    return {
        "slug": tenant.slug,
        "header_background": str(b[CHAT_HEADER_BACKGROUND_KEY]),
        "welcome_title": str(b[CHAT_WELCOME_TITLE_KEY]),
        "welcome_subtitle": str(b[CHAT_WELCOME_SUBTITLE_KEY]),
        "logo_url": logo_url,
        "has_custom_logo": bool(b.get(CHAT_LOGO_FILE_KEY)),
        "favicon_url": favicon_url,
        "has_custom_favicon": bool(b.get(CHAT_FAVICON_FILE_KEY)),
        "quick_actions": list(b.get(CHAT_QUICK_ACTIONS_KEY) or DEFAULT_QUICK_ACTIONS),
    }
