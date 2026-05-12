"""Auth HTTP flow against a real Postgres (skipped if DB unavailable)."""

from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from hospitai.api.main import app
from hospitai.infrastructure.db.models.tenant import Tenant
from hospitai.infrastructure.db.session import get_session_factory


async def _ensure_pytest_tenant() -> str:
    slug = "pytest-hospital"
    factory = get_session_factory()
    async with factory() as session:
        existing = await session.execute(select(Tenant).where(Tenant.slug == slug))
        if existing.scalar_one_or_none() is None:
            session.add(Tenant(name="Pytest Hospital", slug=slug, is_active=True))
            await session.commit()
    return slug


@pytest.mark.asyncio
async def test_register_login_me_and_admin_forbidden() -> None:
    try:
        await _ensure_pytest_tenant()
    except Exception:
        pytest.skip("Database not reachable for integration test")

    slug = "pytest-hospital"
    email = f"user-{uuid.uuid4().hex[:10]}@example.com"
    password = "testpass123456"

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        reg = await client.post(
            "/api/v1/auth/register",
            json={
                "tenant_slug": slug,
                "email": email,
                "password": password,
                "full_name": "Integration User",
            },
        )
        assert reg.status_code == 201, reg.text
        tokens = reg.json()
        assert "access_token" in tokens

        me = await client.get(
            "/api/v1/users/me",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        assert me.status_code == 200
        assert me.json()["email"] == email.lower()

        admin = await client.get(
            "/api/v1/admin/ping",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        assert admin.status_code == 403

        login = await client.post(
            "/api/v1/auth/login",
            json={"tenant_slug": slug, "email": email, "password": password},
        )
        assert login.status_code == 200
        refresh = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": login.json()["refresh_token"]},
        )
        assert refresh.status_code == 200


@pytest.mark.asyncio
async def test_internal_ping_without_key_returns_503() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/api/v1/internal/ping")
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "internal_disabled"
