"""API v1 smoke routes."""

from __future__ import annotations

from fastapi import APIRouter

from hospitai import __version__

router = APIRouter(tags=["v1"])


@router.get("/ping")
async def ping() -> dict[str, str]:
    return {"message": "pong", "api_version": "v1", "service_version": __version__}
