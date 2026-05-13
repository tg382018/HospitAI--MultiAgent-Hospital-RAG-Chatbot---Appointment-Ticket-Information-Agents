"""RAG application service — document ingestion, retrieval, and management.

Orchestrates the full pipeline:
  text extraction → chunking → embedding → vector store → SQL tracking
"""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

import structlog
from hospitai_agent.chunking import chunk_text
from hospitai_agent.embeddings import embed_single, embed_texts
from hospitai_agent.vector_db import (
    add_chunks_to_collection,
    delete_document_vectors,
    query_collection,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from hospitai.application.errors import DomainError
from hospitai.infrastructure.db.models.document import Document, DocumentChunk, DocumentStatus
from hospitai.infrastructure.db.models.tenant import Tenant

log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Text extraction helpers
# ---------------------------------------------------------------------------

_ALLOWED_TEXT_TYPES = {".txt", ".md", ".faq"}


async def _extract_text_from_file(file_path: Path, mime_type: str | None) -> str:
    """Extract raw text content from a file.

    Supports plain text, markdown, and FAQ files natively.
    PDF/DOCX support can be added with additional libraries.
    """
    suffix = file_path.suffix.lower()

    if suffix in _ALLOWED_TEXT_TYPES or (mime_type and mime_type.startswith("text/")):
        return file_path.read_text(encoding="utf-8", errors="replace")

    if suffix == ".pdf":
        # Placeholder for PDF extraction — requires pypdf or similar
        raise DomainError(
            "unsupported_format",
            "PDF extraction not yet configured. Upload as .txt or .md for now.",
            status_code=422,
        )

    if suffix in (".docx", ".doc"):
        raise DomainError(
            "unsupported_format",
            "DOCX extraction not yet configured. Upload as .txt or .md for now.",
            status_code=422,
        )

    raise DomainError(
        "unsupported_format",
        f"Unsupported file format: {suffix}",
        status_code=422,
    )


async def _extract_text_from_content(content: str, source_type: str) -> str:
    """Return content directly (already text)."""
    return content


# ---------------------------------------------------------------------------
# Ingestion pipeline
# ---------------------------------------------------------------------------


async def ingest_document(
    session: AsyncSession,
    *,
    tenant: Tenant,
    title: str,
    source_type: str,
    file_path: str | None = None,
    content: str | None = None,
    mime_type: str | None = None,
    file_size_bytes: int | None = None,
    source_url: str | None = None,
    extra_metadata: str | None = None,
) -> Document:
    """Ingest a document into the RAG pipeline.

    Steps:
    1. Create a Document record (status=pending)
    2. Extract text from file/content
    3. Chunk the text
    4. Generate embeddings (async via to_thread)
    5. Store vectors in ChromaDB (async via to_thread)
    6. Create DocumentChunk records
    7. Update Document status to completed

    All steps are wrapped in a single transaction.
    """
    # 1. Create tracking record
    doc = Document(
        tenant_id=tenant.id,
        title=title.strip(),
        source_type=source_type,
        source_url=source_url,
        file_path=file_path,
        mime_type=mime_type,
        file_size_bytes=file_size_bytes,
        status=DocumentStatus.PROCESSING.value,
        extra_metadata=extra_metadata,
    )
    session.add(doc)
    await session.flush()
    await session.refresh(doc)

    try:
        # 2. Extract text
        if file_path:
            raw_text = await _extract_text_from_file(Path(file_path), mime_type)
        elif content:
            raw_text = await _extract_text_from_content(content, source_type)
        else:
            raise DomainError(
                "missing_input",
                "Either file_path or content must be provided",
                status_code=422,
            )

        if not raw_text.strip():
            raise DomainError(
                "empty_document",
                "Document contains no extractable text",
                status_code=422,
            )

        # 3. Chunk
        chunks = await asyncio.to_thread(chunk_text, raw_text)
        if not chunks:
            raise DomainError(
                "empty_document",
                "Chunking produced no results",
                status_code=422,
            )

        # 4. Generate embeddings (CPU/network-bound → to_thread)
        chunk_texts = [c["content"] for c in chunks]
        embeddings = await asyncio.to_thread(embed_texts, chunk_texts)

        # 5. Store vectors in ChromaDB
        vector_ids = await asyncio.to_thread(
            add_chunks_to_collection,
            tenant.slug,
            document_id=doc.id,
            chunks=chunk_texts,
            embeddings=embeddings,
            metadatas=[
                {
                    "document_id": str(doc.id),
                    "title": title,
                    "source_type": source_type,
                    "chunk_index": c["chunk_index"],
                }
                for c in chunks
            ],
        )

        # 6. Create chunk records
        for i, chunk in enumerate(chunks):
            db_chunk = DocumentChunk(
                document_id=doc.id,
                tenant_id=tenant.id,
                chunk_index=chunk["chunk_index"],
                content=chunk["content"],
                token_count=chunk["token_count"],
                vector_id=vector_ids[i] if i < len(vector_ids) else None,
            )
            session.add(db_chunk)

        # 7. Update document status
        doc.status = DocumentStatus.COMPLETED.value
        doc.chunk_count = len(chunks)
        await session.flush()

        log.info(
            "document_ingested",
            document_id=str(doc.id),
            tenant_slug=tenant.slug,
            chunks=len(chunks),
        )

    except DomainError:
        raise
    except Exception as exc:
        doc.status = DocumentStatus.FAILED.value
        doc.error_message = str(exc)[:2000]
        await session.flush()
        log.error(
            "document_ingestion_failed",
            document_id=str(doc.id),
            error=str(exc),
        )
        raise DomainError(
            "ingestion_failed",
            f"Document ingestion failed: {exc!s}",
            status_code=500,
        ) from exc

    return doc


async def ingest_text(
    session: AsyncSession,
    *,
    tenant: Tenant,
    title: str,
    content: str,
    source_type: str = "manual",
    extra_metadata: str | None = None,
) -> Document:
    """Convenience wrapper: ingest plain text directly (FAQ, policy, etc.)."""
    return await ingest_document(
        session,
        tenant=tenant,
        title=title,
        source_type=source_type,
        content=content,
        extra_metadata=extra_metadata,
    )


# ---------------------------------------------------------------------------
# Deletion
# ---------------------------------------------------------------------------


async def delete_document(
    session: AsyncSession,
    *,
    tenant: Tenant,
    document_id: uuid.UUID,
) -> None:
    """Delete a document and all its chunks from both SQL and vector store."""
    stmt = select(Document).where(Document.id == document_id, Document.tenant_id == tenant.id)
    result = await session.execute(stmt)
    doc = result.scalar_one_or_none()
    if doc is None:
        raise DomainError("document_not_found", "Document not found", status_code=404)

    # Remove vectors from ChromaDB
    await asyncio.to_thread(delete_document_vectors, tenant.slug, document_id)

    # Remove SQL records (chunks cascade)
    await session.delete(doc)
    await session.flush()

    log.info("document_deleted", document_id=str(document_id), tenant_slug=tenant.slug)


# ---------------------------------------------------------------------------
# Listing / querying
# ---------------------------------------------------------------------------


async def list_documents(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    status: str | None = None,
    limit: int = 50,
) -> list[Document]:
    """List all documents for a tenant, optionally filtered by status."""
    stmt = select(Document).where(Document.tenant_id == tenant_id)
    if status:
        stmt = stmt.where(Document.status == status)
    stmt = stmt.order_by(Document.created_at.desc()).limit(min(limit, 200))
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_document(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    document_id: uuid.UUID,
) -> Document:
    """Get a single document by ID within a tenant."""
    stmt = select(Document).where(Document.id == document_id, Document.tenant_id == tenant_id)
    result = await session.execute(stmt)
    doc = result.scalar_one_or_none()
    if doc is None:
        raise DomainError("document_not_found", "Document not found", status_code=404)
    return doc


async def retrieve_context(
    tenant_slug: str,
    *,
    query: str,
    n_results: int = 5,
) -> list[dict]:
    """Retrieve relevant chunks for a query from the tenant's vector store.

    Returns a list of dicts with content, metadata, and distance.
    This is the function the LangGraph agent will call.
    """
    query_embedding = await asyncio.to_thread(embed_single, query)
    results = await asyncio.to_thread(
        query_collection,
        tenant_slug,
        query_embedding=query_embedding,
        n_results=n_results,
    )

    # Normalize ChromaDB output
    documents = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]

    contexts: list[dict] = []
    for i, doc_text in enumerate(documents):
        contexts.append(
            {
                "content": doc_text,
                "metadata": metadatas[i] if i < len(metadatas) else {},
                "distance": distances[i] if i < len(distances) else None,
            }
        )

    return contexts
