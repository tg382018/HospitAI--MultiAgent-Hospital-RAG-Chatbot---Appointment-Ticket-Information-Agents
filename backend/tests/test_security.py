"""Unit tests for password hashing and JWT helpers."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from hospitai.infrastructure.security.jwt_tokens import (
    TokenError,
    create_access_token,
    decode_access_token,
)
from hospitai.infrastructure.security.passwords import hash_password, verify_password
from hospitai.infrastructure.settings import Settings


def test_password_hash_roundtrip() -> None:
    h = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", h)
    assert not verify_password("wrong", h)


def test_password_verify_empty_hash() -> None:
    assert not verify_password("x", "")


def test_jwt_access_roundtrip() -> None:
    settings = Settings(
        database_url="postgresql+asyncpg://u:p@localhost/db",
        jwt_secret="unit-test-secret-32-chars-minimum!!",
        environment="development",
        log_level="INFO",
        cors_origins="http://localhost",
        jwt_algorithm="HS256",
        access_token_expire_minutes=30,
        refresh_token_expire_days=7,
        internal_api_key=None,
        allow_open_registration=True,
    )
    uid = uuid.uuid4()
    tid = uuid.uuid4()
    token = create_access_token(
        user_id=uid,
        tenant_id=tid,
        role="patient",
        email="a@b.com",
        settings=settings,
    )
    claims = decode_access_token(token, settings)
    assert claims.user_id == uid
    assert claims.tenant_id == tid
    assert claims.role == "patient"
    assert claims.email == "a@b.com"


def test_jwt_expired_rejected() -> None:
    settings = Settings(
        database_url="postgresql+asyncpg://u:p@localhost/db",
        jwt_secret="unit-test-secret-32-chars-minimum!!",
        environment="development",
        log_level="INFO",
        cors_origins="http://localhost",
        jwt_algorithm="HS256",
        access_token_expire_minutes=30,
        refresh_token_expire_days=7,
        internal_api_key=None,
        allow_open_registration=True,
    )
    import jwt as pyjwt

    past = datetime.now(UTC) - timedelta(hours=1)
    exp = past + timedelta(seconds=-30)
    payload = {
        "sub": str(uuid.uuid4()),
        "tid": str(uuid.uuid4()),
        "role": "patient",
        "email": "a@b.com",
        "typ": "access",
        "iat": int(past.timestamp()),
        "exp": int(exp.timestamp()),
        "iss": "hospitai",
    }
    token = pyjwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    with pytest.raises(TokenError):
        decode_access_token(token, settings)
