"""API version 1 router tree."""

from __future__ import annotations

from fastapi import APIRouter

from hospitai.api.routers.v1 import ping

api_v1 = APIRouter(prefix="/api/v1")
api_v1.include_router(ping.router)
