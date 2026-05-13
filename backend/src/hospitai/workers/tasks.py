"""Celery task definitions."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from hospitai.application.rag import reindex_document_embeddings
from hospitai.infrastructure.settings import get_settings
from hospitai.workers.bootstrap import configure_worker_environment
from hospitai.workers.celery_app import celery_app

log = structlog.get_logger(__name__)


@celery_app.task(name="hospitai.workers.ping")
def ping() -> dict[str, bool]:
    """Cheap health check for broker + worker."""
    return {"ok": True}


async def _run_reindex(document_id: uuid.UUID) -> dict[str, Any]:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with factory() as session:
            doc = await reindex_document_embeddings(session, document_id=document_id)
            await session.commit()
            return {
                "document_id": str(doc.id),
                "tenant_id": str(doc.tenant_id),
                "chunk_count": doc.chunk_count,
                "status": doc.status,
            }
    finally:
        await engine.dispose()


@celery_app.task(name="hospitai.workers.reindex_document_embeddings", bind=True)
def reindex_document_embeddings_task(self, document_id: str) -> dict[str, Any]:
    """Recompute Chroma embeddings from existing `rag_document_chunks` rows."""
    configure_worker_environment()
    try:
        doc_uuid = uuid.UUID(document_id)
    except ValueError as e:
        raise ValueError(f"Invalid document_id: {document_id!r}") from e
    log.info("reindex_task_started", document_id=document_id, task_id=self.request.id)
    result = asyncio.run(_run_reindex(doc_uuid))
    log.info("reindex_task_finished", document_id=document_id, task_id=self.request.id)
    return result
