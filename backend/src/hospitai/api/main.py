"""FastAPI application factory."""

from __future__ import annotations

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from hospitai.api.errors import register_exception_handlers
from hospitai.api.middleware.request_id import RequestIdMiddleware
from hospitai.api.routers import health
from hospitai.api.routers.v1 import api_v1
from hospitai.infrastructure.db.session import dispose_engine
from hospitai.infrastructure.logging import setup_logging
from hospitai.infrastructure.settings import get_settings

log = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = get_settings()
    setup_logging(settings)
    log.info("app_startup", environment=settings.environment)
    yield
    await dispose_engine()
    log.info("app_shutdown")


def create_app() -> FastAPI:
    settings = get_settings()
    docs_kwargs: dict[str, str | None] = {}
    if settings.environment == "production":
        docs_kwargs = {"openapi_url": None, "docs_url": None, "redoc_url": None}

    app = FastAPI(
        title="HospitAI API",
        description="Hospital AI Agent Platform backend",
        version="0.0.1",
        lifespan=lifespan,
        **docs_kwargs,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestIdMiddleware)
    register_exception_handlers(app)
    app.include_router(health.router)
    app.include_router(api_v1)
    return app


app = create_app()
