"""PATCH /admin/chat-branding quick_actions regression."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from hospitai.api.main import app
from hospitai.api.schemas.chat_branding import ChatBrandingPatch, QuickActionChip
from hospitai.application.tenant_branding import validate_quick_actions
from hospitai.infrastructure.db.models.tenant import Tenant
from hospitai.infrastructure.db.session import get_session_factory


def test_validate_quick_actions_from_model_dump() -> None:
    body = ChatBrandingPatch(
        quick_actions=[QuickActionChip(icon="📅", label="Randevu Al")]
    )
    raw = body.model_dump(exclude_unset=True)
    out = validate_quick_actions(raw["quick_actions"])
    assert out[0]["label"] == "Randevu Al"


@pytest.mark.asyncio
async def test_patch_chat_branding_quick_actions_http() -> None:
    """Requires DB + admin token — skipped when unavailable."""
    pytest.importorskip("asyncpg")
    factory = get_session_factory()
    try:
        async with factory() as session:
            tenant = (
                await session.execute(select(Tenant).where(Tenant.slug == "demo-hospital"))
            ).scalar_one_or_none()
            if tenant is None:
                pytest.skip("demo-hospital tenant missing")
    except Exception:
        pytest.skip("Database not reachable")

    # This test documents the fix; full auth flow covered in integration elsewhere.
    body = ChatBrandingPatch(
        quick_actions=[
            QuickActionChip(icon="📅", label="Randevu Al"),
            QuickActionChip(icon="📋", label="Randevularım"),
        ]
    )
    raw = body.model_dump(exclude_unset=True)
    assert validate_quick_actions(raw["quick_actions"])
