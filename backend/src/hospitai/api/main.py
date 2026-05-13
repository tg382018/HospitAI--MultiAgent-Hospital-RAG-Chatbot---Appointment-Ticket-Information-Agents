"""FastAPI application factory."""

from __future__ import annotations

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from hospitai_agent.graph import configure_workflow_tools
from hospitai_agent.llm_profile import LLMProfile, configure_llm_profile
from hospitai_agent.rag_profile import RagInfrastructureProfile, configure_rag_profile

from hospitai.api.errors import register_exception_handlers
from hospitai.api.limiter import limiter
from hospitai.api.middleware.request_id import RequestIdMiddleware
from hospitai.api.routers import health
from hospitai.api.routers.v1 import api_v1
from hospitai.application.chat.tools import make_workflow_tools
from hospitai.infrastructure.db.session import dispose_engine
from hospitai.infrastructure.logging import setup_logging
from hospitai.infrastructure.settings import get_settings

log = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = get_settings()
    configure_llm_profile(
        LLMProfile(
            llm_model=settings.llm_model,
            llm_api_key=settings.llm_api_key,
            llm_base_url=settings.llm_base_url,
            llm_temperature=settings.llm_temperature,
            embedding_api_key=settings.embedding_api_key,
        )
    )
    configure_rag_profile(
        RagInfrastructureProfile(
            chroma_host=settings.chroma_host,
            chroma_port=settings.chroma_port,
            chroma_collection_prefix=settings.chroma_collection_prefix,
            embedding_model=settings.embedding_model,
            embedding_api_key=settings.embedding_api_key,
            embedding_dimensions=settings.embedding_dimensions,
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
        )
    )
    configure_workflow_tools(make_workflow_tools())
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
    app.state.limiter = limiter
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
