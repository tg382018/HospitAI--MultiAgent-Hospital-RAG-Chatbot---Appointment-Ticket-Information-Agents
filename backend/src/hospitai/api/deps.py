"""FastAPI dependencies."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from hospitai.api.errors import AppError
from hospitai.application.auth import get_user_for_claims
from hospitai.infrastructure.db.models.enums import UserRole
from hospitai.infrastructure.db.models.user import User
from hospitai.infrastructure.db.session import get_session
from hospitai.infrastructure.security.jwt_tokens import TokenError, decode_access_token
from hospitai.infrastructure.settings import Settings, get_settings

SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]

_bearer_optional = HTTPBearer(auto_error=False)
_bearer_required = HTTPBearer(auto_error=True)


async def get_bearer_token_optional(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_optional)],
) -> str | None:
    return credentials.credentials if credentials else None


async def get_bearer_token(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer_required)],
) -> str:
    return credentials.credentials


async def get_current_user(
    session: SessionDep,
    settings: SettingsDep,
    token: Annotated[str, Depends(get_bearer_token)],
) -> User:
    try:
        claims = decode_access_token(token, settings)
    except TokenError as e:
        raise AppError("invalid_token", "Invalid or expired access token", status_code=401) from e
    user = await get_user_for_claims(
        session,
        user_id=claims.user_id,
        tenant_id=claims.tenant_id,
    )
    if user is None:
        raise AppError("invalid_token", "User not found or inactive", status_code=401)
    if user.role.value != claims.role:
        raise AppError(
            "invalid_token",
            "Token is out of date; please sign in again",
            status_code=401,
        )
    return user


async def get_current_user_optional(
    session: SessionDep,
    settings: SettingsDep,
    token: Annotated[str | None, Depends(get_bearer_token_optional)],
) -> User | None:
    if token is None:
        return None
    try:
        claims = decode_access_token(token, settings)
    except TokenError:
        return None
    return await get_user_for_claims(
        session,
        user_id=claims.user_id,
        tenant_id=claims.tenant_id,
    )


CurrentUser = Annotated[User, Depends(get_current_user)]
OptionalUser = Annotated[User | None, Depends(get_current_user_optional)]


def require_roles(*roles: UserRole) -> Callable[..., User]:
    allowed = frozenset(roles)

    async def _dep(user: User = Depends(get_current_user)) -> User:  # noqa: B008
        if user.role not in allowed:
            raise AppError(
                "forbidden",
                "Insufficient permission for this resource",
                status_code=403,
            )
        return user

    return _dep


async def require_internal_service(
    settings: SettingsDep,
    x_internal_key: Annotated[str | None, Header(alias="X-Internal-Key")] = None,
) -> bool:
    """Validates ``X-Internal-Key`` when ``INTERNAL_API_KEY`` is set (workers / tool bridge)."""
    if not settings.internal_api_key:
        raise AppError(
            "internal_disabled",
            "Internal API is not configured on this deployment",
            status_code=503,
        )
    if not x_internal_key or x_internal_key != settings.internal_api_key:
        raise AppError(
            "forbidden",
            "Invalid internal service credentials",
            status_code=403,
        )
    return True


InternalServiceDep = Annotated[bool, Depends(require_internal_service)]
