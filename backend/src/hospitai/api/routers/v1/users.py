"""Authenticated user profile."""

from __future__ import annotations

from fastapi import APIRouter

from hospitai.api.deps import CurrentUser
from hospitai.api.schemas.auth import UserMeResponse

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserMeResponse)
async def read_me(user: CurrentUser) -> UserMeResponse:
    return UserMeResponse.model_validate(user)
