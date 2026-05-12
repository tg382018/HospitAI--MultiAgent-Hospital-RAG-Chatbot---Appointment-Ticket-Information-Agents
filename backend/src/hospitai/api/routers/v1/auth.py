"""Auth: login, register, refresh."""

from __future__ import annotations

from fastapi import APIRouter

from hospitai.api.deps import SessionDep, SettingsDep
from hospitai.api.errors import AppError
from hospitai.api.schemas.auth import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
)
from hospitai.application.auth import (
    AuthError,
    authenticate_user,
    get_user_for_claims,
    issue_token_pair,
    register_patient,
)
from hospitai.infrastructure.security.jwt_tokens import TokenError, decode_refresh_token

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, session: SessionDep, settings: SettingsDep) -> TokenResponse:
    try:
        user = await authenticate_user(
            session,
            tenant_slug=body.tenant_slug,
            email=str(body.email),
            password=body.password,
        )
    except AuthError as e:
        raise AppError(e.code, e.message, status_code=e.status_code) from e
    access, refresh = issue_token_pair(user, settings)
    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        expires_in=settings.access_token_expire_minutes * 60,
    )


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(
    body: RegisterRequest,
    session: SessionDep,
    settings: SettingsDep,
) -> TokenResponse:
    try:
        user = await register_patient(
            session,
            settings,
            tenant_slug=body.tenant_slug,
            email=str(body.email),
            password=body.password,
            full_name=body.full_name,
        )
        await session.commit()
    except AuthError as e:
        await session.rollback()
        raise AppError(e.code, e.message, status_code=e.status_code) from e
    access, refresh = issue_token_pair(user, settings)
    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        expires_in=settings.access_token_expire_minutes * 60,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    body: RefreshRequest,
    session: SessionDep,
    settings: SettingsDep,
) -> TokenResponse:
    try:
        claims = decode_refresh_token(body.refresh_token, settings)
    except TokenError:
        raise AppError(
            "invalid_token",
            "Invalid or expired refresh token",
            status_code=401,
        ) from None
    user = await get_user_for_claims(
        session,
        user_id=claims.user_id,
        tenant_id=claims.tenant_id,
    )
    if user is None:
        raise AppError("invalid_token", "User not found or inactive", status_code=401)
    access, refresh = issue_token_pair(user, settings)
    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        expires_in=settings.access_token_expire_minutes * 60,
    )
