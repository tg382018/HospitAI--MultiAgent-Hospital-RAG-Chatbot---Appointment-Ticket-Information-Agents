"""Liveness / readiness probes."""

from __future__ import annotations

import structlog
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from hospitai.infrastructure.db.session import get_engine

router = APIRouter(tags=["health"])
log = structlog.get_logger(__name__)


@router.get("/healthz")
async def liveness() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz", response_model=None)
async def readiness():
    try:
        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        log.exception("readiness_database_failed")
        return JSONResponse(
            status_code=503,
            content={"ok": False, "database": "unavailable"},
        )
    return {"ok": True, "database": "up"}
