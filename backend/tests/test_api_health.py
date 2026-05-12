"""HTTP API integration tests (async ASGI transport)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from hospitai.api.main import app


@pytest.mark.asyncio
async def test_healthz() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_v1_ping() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/api/v1/ping")
    assert r.status_code == 200
    data = r.json()
    assert data["message"] == "pong"
    assert data["api_version"] == "v1"
    assert "service_version" in data


@pytest.mark.asyncio
async def test_request_id_roundtrip() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/healthz", headers={"X-Request-ID": "client-req-1"})
    assert r.headers.get("X-Request-ID") == "client-req-1"


@pytest.mark.asyncio
async def test_readyz_returns_json() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/readyz")
    assert r.status_code in (200, 503)
    body = r.json()
    assert "ok" in body
