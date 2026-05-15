"""Tenant chat branding helpers."""

from __future__ import annotations

import pytest

from hospitai.application.tenant_branding import (
    DEFAULT_QUICK_ACTIONS,
    DEFAULT_WELCOME_TITLE,
    effective_branding,
    merge_branding_patch,
    validate_header_background,
    validate_quick_actions,
    validate_welcome_text,
)


class _FakeTenant:
    def __init__(self, branding: dict | None) -> None:
        self.branding = branding
        self.slug = "demo-hospital"
        self.updated_at = None


def test_effective_branding_defaults() -> None:
    b = effective_branding(_FakeTenant(None))
    assert b["chat_welcome_title"] == DEFAULT_WELCOME_TITLE


def test_validate_header_background_rejects_script() -> None:
    with pytest.raises(ValueError):
        validate_header_background("#fff; background: url(http://evil)")


def test_merge_branding_patch() -> None:
    merged = merge_branding_patch(None, {"chat_welcome_title": "Selam"})
    assert merged["chat_welcome_title"] == "Selam"
    assert "chat_welcome_subtitle" in merged


def test_validate_welcome_text_nonempty() -> None:
    with pytest.raises(ValueError):
        validate_welcome_text("   ", field="welcome_title")


def test_validate_quick_actions_defaults() -> None:
    out = validate_quick_actions(DEFAULT_QUICK_ACTIONS)
    assert len(out) == 4
    assert out[0]["label"] == "Randevu Al"


def test_validate_quick_actions_duplicate_label() -> None:
    with pytest.raises(ValueError):
        validate_quick_actions(
            [{"icon": "📅", "label": "A"}, {"icon": "📋", "label": "a"}]
        )
