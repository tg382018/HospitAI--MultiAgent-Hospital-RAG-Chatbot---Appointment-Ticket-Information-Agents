"""Admin registration (key-gated) tests."""

from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from hospitai.api.deps import get_settings
from hospitai.api.main import app
from hospitai.application.auth import AuthError
from hospitai.infrastructure.db.models.tenant import Tenant
from hospitai.infrastructure.db.session import get_session_factory
from hospitai.infrastructure.settings import Settings


async def _ensure_pytest_tenant() -> str:
    slug = "pytest-hospital"
    factory = get_session_factory()
    async with factory() as session:
        existing = await session.execute(select(Tenant).where(Tenant.slug == slug))
        if existing.scalar_one_or_none() is None:
            session.add(Tenant(name="Pytest Hospital", slug=slug, is_active=True))
            await session.commit()
    return slug


def test_verify_admin_registration_key_rejects_wrong_key() -> None:
    settings = Settings(admin_registration_key="mynewkey")
    with pytest.raises(AuthError) as exc:
        from hospitai.application.auth import _verify_admin_registration_key

        _verify_admin_registration_key(settings, "wrong")
    assert exc.value.code == "invalid_registration_key"
    assert exc.value.status_code == 403


def test_verify_admin_registration_key_disabled_when_unset() -> None:
    settings = Settings(admin_registration_key=None)
    with pytest.raises(AuthError) as exc:
        from hospitai.application.auth import _verify_admin_registration_key

        _verify_admin_registration_key(settings, "anything")
    assert exc.value.code == "admin_registration_disabled"
    assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_register_admin_http_flow() -> None:
    try:
        slug = await _ensure_pytest_tenant()
    except Exception:
        pytest.skip("Database not reachable for integration test")

    base = get_settings()
    settings = base.model_copy(update={"admin_registration_key": "mynewkey"})
    app.dependency_overrides[get_settings] = lambda: settings

    email = f"admin-{uuid.uuid4().hex[:10]}@example.com"
    password = "adminpass123456"

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            bad = await client.post(
                "/api/v1/auth/register-admin",
                json={
                    "tenant_slug": slug,
                    "email": email,
                    "password": password,
                    "key": "wrong-key",
                },
            )
            assert bad.status_code == 403
            assert bad.json()["error"]["code"] == "invalid_registration_key"

            reg = await client.post(
                "/api/v1/auth/register-admin",
                json={
                    "tenant_slug": slug,
                    "email": email,
                    "password": password,
                    "key": "mynewkey",
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
            assert me.json()["role"] == "admin"
            assert me.json()["email"] == email.lower()

            admin_ping = await client.get(
                "/api/v1/admin/ping",
                headers={"Authorization": f"Bearer {tokens['access_token']}"},
            )
            assert admin_ping.status_code == 200
    finally:
        app.dependency_overrides.pop(get_settings, None)
