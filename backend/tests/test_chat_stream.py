"""Unit tests for the /chat/stream SSE endpoint.

These tests mock the DB layer and the LangGraph workflow to verify:
- Correct SSE event order and format (meta → token → final)
- Limit-reached path (meta → final with limit_reached intent)
- Database error produces 503 AppError
- Guest tenant resolution via X-Tenant-Slug header
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from hospitai.api.main import app

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CONV_ID = str(uuid.uuid4())
_TENANT_ID = uuid.uuid4()
_TENANT_SLUG = "test-hospital"


def _make_fake_tenant() -> MagicMock:
    t = MagicMock()
    t.id = _TENANT_ID
    t.slug = _TENANT_SLUG
    t.settings = None
    t.is_active = True
    return t


def _make_fake_conv() -> MagicMock:
    c = MagicMock()
    c.id = uuid.UUID(_CONV_ID)
    c.extra = {}
    return c


async def _fake_iter_sse(**_kwargs) -> AsyncIterator[str]:
    """Minimal SSE generator: token then final."""
    yield f"event: token\ndata: {json.dumps({'text': 'Merhaba'})}\n\n"
    yield (
        "event: final\n"
        "data: "
        + json.dumps(
            {
                "response": "Merhaba, size nasıl yardımcı olabilirim?",
                "intent": "general",
                "sources": [],
                "rag_used": False,
                "escalated": False,
                "safety_flag": False,
                "safety_reason": "",
            }
        )
        + "\n\n"
    )


def _parse_sse(body: bytes) -> list[dict]:
    """Parse raw SSE body into a list of {event, data} dicts."""
    events: list[dict] = []
    for frame in body.decode().split("\n\n"):
        frame = frame.strip()
        if not frame:
            continue
        ev = ""
        data = ""
        for line in frame.splitlines():
            if line.startswith("event:"):
                ev = line[6:].strip()
            elif line.startswith("data:"):
                data = line[5:].strip()
        if ev and data:
            events.append({"event": ev, "data": json.loads(data)})
    return events


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chat_stream_sse_event_order(monkeypatch) -> None:
    """Happy path: meta → token → final events arrive in the correct order."""
    fake_tenant = _make_fake_tenant()
    fake_conv = _make_fake_conv()

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.commit = AsyncMock()

    mock_factory = MagicMock(return_value=mock_session)

    async def fake_resolve(session, *, user, x_tenant_slug, settings):
        return fake_tenant, _TENANT_ID, _TENANT_SLUG

    async def fake_agent_overrides(session, *, tenant_id):
        return _TENANT_SLUG, {}, 20

    async def fake_get_or_create(session, *, tenant_id, user_id, conversation_id):
        return fake_conv

    async def fake_load_memory(cs, session, conv_id, *, max_messages):
        return cs

    async def fake_check_limit(session, *, conversation_id, tenant_id, max_messages):
        return None

    async def fake_save_message(session, *, conversation_id, tenant_id, role, content):
        pass

    async def fake_write_audit(*args, **kwargs):
        pass

    monkeypatch.setattr("hospitai.api.routers.v1.chat.get_session_factory", lambda: mock_factory)
    monkeypatch.setattr("hospitai.api.routers.v1.chat._resolve_tenant_for_chat", fake_resolve)
    monkeypatch.setattr(
        "hospitai.api.routers.v1.chat._tenant_slug_and_agent_overrides", fake_agent_overrides
    )
    monkeypatch.setattr(
        "hospitai.api.routers.v1.chat.get_or_create_conversation", fake_get_or_create
    )
    monkeypatch.setattr("hospitai.api.routers.v1.chat.load_memory", fake_load_memory)
    monkeypatch.setattr("hospitai.api.routers.v1.chat.check_conversation_limit", fake_check_limit)
    monkeypatch.setattr("hospitai.api.routers.v1.chat.save_message", fake_save_message)
    monkeypatch.setattr("hospitai.api.routers.v1.chat.write_audit_log", fake_write_audit)
    monkeypatch.setattr("hospitai.api.routers.v1.chat.iter_chat_sse", _fake_iter_sse)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            "/api/v1/chat/stream",
            json={"message": "merhaba"},
            headers={"X-Tenant-Slug": _TENANT_SLUG},
        )

    assert r.status_code == 200
    assert "text/event-stream" in r.headers["content-type"]

    events = _parse_sse(r.content)
    event_names = [e["event"] for e in events]

    assert event_names[0] == "meta"
    assert events[0]["data"]["conversation_id"] == _CONV_ID

    assert "token" in event_names
    final_events = [e for e in events if e["event"] == "final"]
    assert len(final_events) == 1
    assert final_events[0]["data"]["intent"] == "general"


@pytest.mark.asyncio
async def test_chat_stream_limit_reached(monkeypatch) -> None:
    """When the conversation limit is reached, stream should emit meta then final(limit_reached)."""
    fake_tenant = _make_fake_tenant()
    fake_conv = _make_fake_conv()

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.commit = AsyncMock()
    mock_factory = MagicMock(return_value=mock_session)

    async def fake_resolve(session, *, user, x_tenant_slug, settings):
        return fake_tenant, _TENANT_ID, _TENANT_SLUG

    async def fake_agent_overrides(session, *, tenant_id):
        return _TENANT_SLUG, {}, 20

    async def fake_get_or_create(session, *, tenant_id, user_id, conversation_id):
        return fake_conv

    async def fake_load_memory(cs, session, conv_id, *, max_messages):
        return cs

    async def fake_check_limit(session, *, conversation_id, tenant_id, max_messages):
        return "Bu konuşma mesaj limitine ulaştı. Lütfen yeni bir konuşma başlatın."

    async def fake_save_message(session, *, conversation_id, tenant_id, role, content):
        pass

    monkeypatch.setattr("hospitai.api.routers.v1.chat.get_session_factory", lambda: mock_factory)
    monkeypatch.setattr("hospitai.api.routers.v1.chat._resolve_tenant_for_chat", fake_resolve)
    monkeypatch.setattr(
        "hospitai.api.routers.v1.chat._tenant_slug_and_agent_overrides", fake_agent_overrides
    )
    monkeypatch.setattr(
        "hospitai.api.routers.v1.chat.get_or_create_conversation", fake_get_or_create
    )
    monkeypatch.setattr("hospitai.api.routers.v1.chat.load_memory", fake_load_memory)
    monkeypatch.setattr("hospitai.api.routers.v1.chat.check_conversation_limit", fake_check_limit)
    monkeypatch.setattr("hospitai.api.routers.v1.chat.save_message", fake_save_message)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            "/api/v1/chat/stream",
            json={"message": "merhaba"},
            headers={"X-Tenant-Slug": _TENANT_SLUG},
        )

    assert r.status_code == 200
    events = _parse_sse(r.content)
    event_names = [e["event"] for e in events]

    assert event_names[0] == "meta"
    final_events = [e for e in events if e["event"] == "final"]
    assert len(final_events) == 1
    assert final_events[0]["data"]["intent"] == "limit_reached"
    assert "token" not in event_names


@pytest.mark.asyncio
async def test_chat_stream_tenant_not_found(monkeypatch) -> None:
    """When tenant is not found, a 404 AppError should be raised before streaming starts."""
    from hospitai.api.errors import AppError

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_factory = MagicMock(return_value=mock_session)

    async def fake_resolve_missing(session, *, user, x_tenant_slug, settings):
        raise AppError("tenant_not_found", "Hastane bulunamadı.", status_code=404)

    monkeypatch.setattr("hospitai.api.routers.v1.chat.get_session_factory", lambda: mock_factory)
    monkeypatch.setattr(
        "hospitai.api.routers.v1.chat._resolve_tenant_for_chat", fake_resolve_missing
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            "/api/v1/chat/stream",
            json={"message": "merhaba"},
            headers={"X-Tenant-Slug": "nonexistent-hospital"},
        )

    assert r.status_code == 404
    body = r.json()
    assert body["error"]["code"] == "tenant_not_found"


@pytest.mark.asyncio
async def test_chat_stream_db_error_returns_503(monkeypatch) -> None:
    """A database error during session setup should return 503 with a generic message."""
    from sqlalchemy.exc import OperationalError

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(
        side_effect=OperationalError("connection refused", None, None)
    )
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_factory = MagicMock(return_value=mock_session)

    monkeypatch.setattr("hospitai.api.routers.v1.chat.get_session_factory", lambda: mock_factory)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            "/api/v1/chat/stream",
            json={"message": "merhaba"},
        )

    assert r.status_code == 503
    body = r.json()
    assert body["error"]["code"] == "database_unavailable"
    # Must NOT expose internal infra details
    assert "docker" not in body["error"]["message"].lower()
    assert "alembic" not in body["error"]["message"].lower()
