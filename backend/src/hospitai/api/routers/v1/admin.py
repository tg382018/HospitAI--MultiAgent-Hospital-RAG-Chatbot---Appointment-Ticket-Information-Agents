"""Admin-only diagnostics."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from hospitai.api.deps import require_roles
from hospitai.infrastructure.db.models.enums import UserRole
from hospitai.infrastructure.db.models.user import User

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/ping")
async def admin_ping(
    _user: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
) -> dict[str, str]:
    return {"message": "ok", "scope": "admin"}
