"""Celery task definitions."""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from hospitai.application.rag import reindex_document_embeddings
from hospitai.infrastructure import hospital_connector as hospital_ext
from hospitai.infrastructure.db.models.tenant import Tenant
from hospitai.infrastructure.settings import get_settings
from hospitai.workers.bootstrap import configure_worker_environment
from hospitai.workers.celery_app import celery_app

log = structlog.get_logger(__name__)


@celery_app.task(name="hospitai.workers.ping")
def ping() -> dict[str, bool]:
    """Cheap health check for broker + worker."""
    return {"ok": True}


@celery_app.task(name="hospitai.workers.notify_domain_event")
def notify_domain_event(tenant_id: str, event_type: str, payload_json: str) -> dict[str, bool]:
    """Async notification hook (e-mail/push later); today: structured log for workers."""
    try:
        payload = json.loads(payload_json)
    except json.JSONDecodeError:
        payload = {"raw": payload_json}
    log.info(
        "domain_event",
        tenant_id=tenant_id,
        event_type=event_type,
        payload=payload,
    )
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


async def _probe_external_hospital_connectivity(tenant_id: uuid.UUID) -> dict[str, Any]:
    """Lightweight GET /v1/doctors from worker (async DB + httpx)."""
    settings = get_settings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with factory() as session:
            row = await session.execute(select(Tenant).where(Tenant.id == tenant_id))
            tenant = row.scalar_one_or_none()
            if tenant is None:
                return {"ok": False, "error": "tenant_not_found", "tenant_id": str(tenant_id)}

            base = (tenant.external_hospital_base_url or "").strip()
            if not base:
                return {
                    "ok": True,
                    "skipped": True,
                    "reason": "no_external_base_url",
                    "tenant_id": str(tenant_id),
                }

            api_key = (tenant.external_hospital_api_key or "").strip() or None
            try:
                doctors = await hospital_ext.fetch_external_doctors(
                    base_url=base,
                    api_key=api_key,
                )
            except Exception as exc:
                log.warning(
                    "external_hospital_probe_http_error",
                    tenant_id=str(tenant_id),
                    error=str(exc),
                )
                return {
                    "ok": False,
                    "error": str(exc),
                    "tenant_id": str(tenant_id),
                }

            return {
                "ok": True,
                "doctor_count": len(doctors),
                "tenant_id": str(tenant_id),
            }
    finally:
        await engine.dispose()


@celery_app.task(name="hospitai.workers.probe_external_hospital_connectivity")
def probe_external_hospital_connectivity_task(tenant_id: str) -> dict[str, Any]:
    """Queue-time probe for external hospital connector (adım 4 örnek akış)."""
    configure_worker_environment()
    try:
        tid = uuid.UUID(tenant_id)
    except ValueError:
        return {"ok": False, "error": "invalid_tenant_id", "tenant_id": tenant_id}

    log.info("external_hospital_probe_started", tenant_id=tenant_id)
    result = asyncio.run(_probe_external_hospital_connectivity(tid))
    log.info(
        "external_hospital_probe_finished",
        tenant_id=tenant_id,
        result_ok=result.get("ok"),
    )
    return result


@celery_app.task(name="hospitai.workers.reindex_document_embeddings", bind=True)
def reindex_document_embeddings_task(self, document_id: str) -> dict[str, Any]:
    """Recompute Chroma embeddings from existing ``document_chunks`` rows."""
    configure_worker_environment()
    try:
        doc_uuid = uuid.UUID(document_id)
    except ValueError as e:
        raise ValueError(f"Invalid document_id: {document_id!r}") from e
    log.info("reindex_task_started", document_id=document_id, task_id=self.request.id)
    result = asyncio.run(_run_reindex(doc_uuid))
    log.info("reindex_task_finished", document_id=document_id, task_id=self.request.id)
    return result
