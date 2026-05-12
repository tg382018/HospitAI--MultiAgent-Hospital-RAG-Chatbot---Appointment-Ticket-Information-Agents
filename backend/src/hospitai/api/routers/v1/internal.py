"""Machine-to-machine entry (Celery, tool runner)."""

from __future__ import annotations

from fastapi import APIRouter

from hospitai.api.deps import InternalServiceDep

router = APIRouter(prefix="/internal", tags=["internal"])


@router.get("/ping")
async def internal_ping(_: InternalServiceDep) -> dict[str, str]:
    return {"message": "ok", "scope": "internal"}
