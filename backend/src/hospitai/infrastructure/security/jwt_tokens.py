"""JWT access / refresh token helpers (HS256)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from jwt import PyJWTError

from hospitai.infrastructure.settings import Settings


class TokenError(ValueError):
    """Invalid or expired token."""


@dataclass(frozen=True)
class AccessClaims:
    user_id: uuid.UUID
    tenant_id: uuid.UUID
    role: str
    email: str


@dataclass(frozen=True)
class RefreshClaims:
    user_id: uuid.UUID
    tenant_id: uuid.UUID


def _now() -> datetime:
    return datetime.now(UTC)


def create_access_token(
    *,
    user_id: uuid.UUID,
    tenant_id: uuid.UUID,
    role: str,
    email: str,
    settings: Settings,
) -> str:
    now = _now()
    exp = now + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {
        "sub": str(user_id),
        "tid": str(tenant_id),
        "role": role,
        "email": email,
        "typ": "access",
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "iss": "hospitai",
    }
    return jwt.encode(
        payload,
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )


def decode_access_token(token: str, settings: Settings) -> AccessClaims:
    try:
        data = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "iat", "sub"]},
        )
    except PyJWTError as e:
        raise TokenError("invalid_access_token") from e
    if data.get("typ") != "access":
        raise TokenError("wrong_token_type")
    try:
        return AccessClaims(
            user_id=uuid.UUID(data["sub"]),
            tenant_id=uuid.UUID(data["tid"]),
            role=str(data["role"]),
            email=str(data["email"]),
        )
    except (KeyError, ValueError) as e:
        raise TokenError("malformed_access_token") from e


def create_refresh_token(
    *,
    user_id: uuid.UUID,
    tenant_id: uuid.UUID,
    settings: Settings,
) -> str:
    now = _now()
    exp = now + timedelta(days=settings.refresh_token_expire_days)
    payload = {
        "sub": str(user_id),
        "tid": str(tenant_id),
        "typ": "refresh",
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "iss": "hospitai",
    }
    return jwt.encode(
        payload,
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )


def decode_refresh_token(token: str, settings: Settings) -> RefreshClaims:
    try:
        data = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "iat", "sub"]},
        )
    except PyJWTError as e:
        raise TokenError("invalid_refresh_token") from e
    if data.get("typ") != "refresh":
        raise TokenError("wrong_token_type")
    try:
        return RefreshClaims(
            user_id=uuid.UUID(data["sub"]),
            tenant_id=uuid.UUID(data["tid"]),
        )
    except (KeyError, ValueError) as e:
        raise TokenError("malformed_refresh_token") from e
