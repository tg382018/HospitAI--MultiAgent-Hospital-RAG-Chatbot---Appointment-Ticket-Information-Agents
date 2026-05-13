"""ChromaDB client — tenant-aware collection management.

Each tenant gets its own ChromaDB collection named:
    {chroma_collection_prefix}_{tenant_slug}

This ensures strict data isolation between tenants in the vector store.
"""

from __future__ import annotations

import uuid

import chromadb
import structlog

from hospitai.infrastructure.settings import get_settings

log = structlog.get_logger(__name__)

_client: chromadb.HttpClient | None = None


def get_chroma_client() -> chromadb.HttpClient:
    """Return a singleton ChromaDB HTTP client (connects to Docker Chroma service)."""
    global _client
    if _client is None:
        settings = get_settings()
        _client = chromadb.HttpClient(
            host=settings.chroma_host,
            port=settings.chroma_port,
        )
        log.info(
            "chroma_connected",
            host=settings.chroma_host,
            port=settings.chroma_port,
        )
    return _client


def tenant_collection_name(tenant_slug: str) -> str:
    """Derive a deterministic ChromaDB collection name for a tenant."""
    prefix = get_settings().chroma_collection_prefix
    return f"{prefix}_{tenant_slug}"


def get_tenant_collection(tenant_slug: str) -> chromadb.Collection:
    """Get or create the ChromaDB collection for a given tenant."""
    client = get_chroma_client()
    name = tenant_collection_name(tenant_slug)
    return client.get_or_create_collection(
        name=name,
        metadata={"hnsw:space": "cosine"},
    )


def delete_tenant_collection(tenant_slug: str) -> None:
    """Delete the entire ChromaDB collection for a tenant (GDPR / data erasure)."""
    client = get_chroma_client()
    name = tenant_collection_name(tenant_slug)
    try:
        client.delete_collection(name)
        log.info("chroma_collection_deleted", collection=name)
    except Exception:
        log.warning("chroma_collection_delete_failed", collection=name)


def build_vector_id(document_id: uuid.UUID, chunk_index: int) -> str:
    """Build a deterministic, globally unique vector ID.

    Format: {document_id}_{chunk_index}
    This makes it easy to delete all vectors of a document by prefix.
    """
    return f"{document_id}_{chunk_index}"


def add_chunks_to_collection(
    tenant_slug: str,
    *,
    document_id: uuid.UUID,
    chunks: list[str],
    embeddings: list[list[float]],
    metadatas: list[dict] | None = None,
) -> list[str]:
    """Add chunk vectors to the tenant's collection.

    Returns a list of vector IDs that were inserted.
    """
    collection = get_tenant_collection(tenant_slug)
    ids = [build_vector_id(document_id, i) for i in range(len(chunks))]

    if metadatas is None:
        metadatas = [{"document_id": str(document_id), "chunk_index": i} for i in range(len(chunks))]
    else:
        for i, m in enumerate(metadatas):
            m.setdefault("document_id", str(document_id))
            m.setdefault("chunk_index", i)

    collection.upsert(
        ids=ids,
        embeddings=embeddings,
        documents=chunks,
        metadatas=metadatas,
    )
    log.info(
        "chroma_chunks_upserted",
        tenant_slug=tenant_slug,
        document_id=str(document_id),
        count=len(chunks),
    )
    return ids


def delete_document_vectors(tenant_slug: str, document_id: uuid.UUID) -> None:
    """Remove all vectors belonging to a document from the tenant's collection."""
    collection = get_tenant_collection(tenant_slug)
    # ChromaDB supports where filter on metadata
    collection.delete(where={"document_id": str(document_id)})
    log.info(
        "chroma_document_vectors_deleted",
        tenant_slug=tenant_slug,
        document_id=str(document_id),
    )


def query_collection(
    tenant_slug: str,
    *,
    query_embedding: list[float],
    n_results: int = 5,
    where: dict | None = None,
) -> dict:
    """Query the tenant collection with an embedding vector.

    Returns ChromaDB result dict with ids, documents, metadatas, distances.
    """
    collection = get_tenant_collection(tenant_slug)
    kwargs: dict = {
        "query_embeddings": [query_embedding],
        "n_results": min(n_results, 20),
    }
    if where:
        kwargs["where"] = where
    results = collection.query(**kwargs)
    return results