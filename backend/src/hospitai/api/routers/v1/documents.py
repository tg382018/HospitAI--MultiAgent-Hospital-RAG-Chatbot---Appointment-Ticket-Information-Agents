"""RAG document management REST API.

Endpoints:
- POST   /documents/ingest-text   → Ingest text content (FAQ, policy, etc.)
- GET    /documents               → List documents for the tenant
- GET    /documents/{id}          → Get a single document
- DELETE /documents/{id}          → Delete a document + its vectors
- POST   /documents/{id}/reindex-embeddings → Queue Celery job to refresh vectors (admin/staff)
- POST   /documents/retrieve      → Retrieve relevant chunks for a query
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query

from hospitai.api.deps import CurrentUser, SessionDep
from hospitai.api.http_mapping import raise_from_domain
from hospitai.api.schemas.documents import (
    DocumentListResponse,
    DocumentResponse,
    IngestTextRequest,
    ReindexQueuedResponse,
    RetrievedChunk,
    RetrieveRequest,
    RetrieveResponse,
)
from hospitai.application.errors import DomainError
from hospitai.application.rag import (
    delete_document,
    get_document,
    ingest_text,
    list_documents,
    retrieve_context,
)
from hospitai.workers.tasks import reindex_document_embeddings_task

router = APIRouter(prefix="/documents", tags=["documents"])


# ---- Ingest text -----------------------------------------------------------


@router.post("/ingest-text", response_model=DocumentResponse, status_code=201)
async def ingest_text_endpoint(
    session: SessionDep,
    current: CurrentUser,
    body: IngestTextRequest,
) -> DocumentResponse:
    """Ingest plain text content (FAQ, policy, manual) into the RAG pipeline.

    Only admin and staff roles can ingest documents.
    """
    from hospitai.infrastructure.db.models.enums import UserRole

    if current.role not in {UserRole.ADMIN, UserRole.STAFF}:
        raise_from_domain(
            DomainError("forbidden", "Only admin/staff can ingest documents", status_code=403)
        )

    # Load tenant
    from sqlalchemy import select

    from hospitai.infrastructure.db.models.tenant import Tenant

    tenant_stmt = select(Tenant).where(Tenant.id == current.tenant_id)
    result = await session.execute(tenant_stmt)
    tenant = result.scalar_one_or_none()
    if tenant is None:
        raise_from_domain(DomainError("tenant_not_found", "Tenant not found", status_code=404))

    try:
        doc = await ingest_text(
            session,
            tenant=tenant,
            title=body.title,
            content=body.content,
            source_type=body.source_type,
            extra_metadata=body.extra_metadata,
        )
        await session.commit()
    except DomainError as e:
        await session.rollback()
        raise_from_domain(e)

    return DocumentResponse.model_validate(doc)


# ---- List documents --------------------------------------------------------


@router.get("", response_model=DocumentListResponse)
async def list_documents_endpoint(
    session: SessionDep,
    current: CurrentUser,
    status: str | None = Query(default=None),
    limit: int = Query(50, ge=1, le=200),
) -> DocumentListResponse:
    """List documents for the current tenant."""
    docs = await list_documents(
        session,
        tenant_id=current.tenant_id,
        status=status,
        limit=limit,
    )
    return DocumentListResponse(documents=[DocumentResponse.model_validate(d) for d in docs])


# ---- Get single document ---------------------------------------------------


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document_endpoint(
    session: SessionDep,
    current: CurrentUser,
    document_id: uuid.UUID,
) -> DocumentResponse:
    """Get a single document by ID."""
    try:
        doc = await get_document(
            session,
            tenant_id=current.tenant_id,
            document_id=document_id,
        )
    except DomainError as e:
        raise_from_domain(e)
    return DocumentResponse.model_validate(doc)


# ---- Delete document -------------------------------------------------------


@router.delete("/{document_id}", status_code=204)
async def delete_document_endpoint(
    session: SessionDep,
    current: CurrentUser,
    document_id: uuid.UUID,
) -> None:
    """Delete a document and all its vector embeddings.

    Only admin/staff can delete documents.
    """
    from hospitai.infrastructure.db.models.enums import UserRole

    if current.role not in {UserRole.ADMIN, UserRole.STAFF}:
        raise_from_domain(
            DomainError("forbidden", "Only admin/staff can delete documents", status_code=403)
        )

    # Load tenant
    from sqlalchemy import select

    from hospitai.infrastructure.db.models.tenant import Tenant

    tenant_stmt = select(Tenant).where(Tenant.id == current.tenant_id)
    result = await session.execute(tenant_stmt)
    tenant = result.scalar_one_or_none()
    if tenant is None:
        raise_from_domain(DomainError("tenant_not_found", "Tenant not found", status_code=404))

    try:
        await delete_document(session, tenant=tenant, document_id=document_id)
        await session.commit()
    except DomainError as e:
        await session.rollback()
        raise_from_domain(e)


# ---- Reindex embeddings (Celery) -------------------------------------------


@router.post(
    "/{document_id}/reindex-embeddings",
    response_model=ReindexQueuedResponse,
    status_code=202,
)
async def reindex_embeddings_endpoint(
    session: SessionDep,
    current: CurrentUser,
    document_id: uuid.UUID,
) -> ReindexQueuedResponse:
    """Queue a Celery job to recompute vectors from stored chunks (embedding model change, repair).

    Admin/staff only. Requires a running worker and Redis broker.
    """
    from hospitai.infrastructure.db.models.enums import UserRole

    if current.role not in {UserRole.ADMIN, UserRole.STAFF}:
        raise_from_domain(
            DomainError("forbidden", "Only admin/staff can reindex documents", status_code=403)
        )

    try:
        await get_document(
            session,
            tenant_id=current.tenant_id,
            document_id=document_id,
        )
    except DomainError as e:
        raise_from_domain(e)

    async_result = reindex_document_embeddings_task.delay(str(document_id))
    return ReindexQueuedResponse(task_id=async_result.id, document_id=document_id)


# ---- RAG retrieval ---------------------------------------------------------


@router.post("/retrieve", response_model=RetrieveResponse)
async def retrieve_endpoint(
    current: CurrentUser,
    body: RetrieveRequest,
) -> RetrieveResponse:
    """Retrieve relevant chunks for a semantic search query.

    All authenticated users can query the RAG pipeline for their tenant.
    """
    from sqlalchemy import select

    from hospitai.infrastructure.db.models.tenant import Tenant
    from hospitai.infrastructure.db.session import get_session_factory

    # We need the tenant slug; resolve it via a quick session
    factory = get_session_factory()
    async with factory() as session:
        tenant_stmt = select(Tenant).where(Tenant.id == current.tenant_id)
        result = await session.execute(tenant_stmt)
        tenant = result.scalar_one_or_none()

    if tenant is None:
        raise_from_domain(DomainError("tenant_not_found", "Tenant not found", status_code=404))

    try:
        results = await retrieve_context(
            tenant.slug,
            query=body.query,
            n_results=body.n_results,
        )
    except Exception as e:
        raise_from_domain(
            DomainError("retrieval_failed", f"RAG retrieval failed: {e!s}", status_code=500)
        )

    return RetrieveResponse(
        query=body.query,
        results=[
            RetrievedChunk(
                content=r["content"],
                metadata=r.get("metadata", {}),
                distance=r.get("distance"),
            )
            for r in results
        ],
    )
