"""ChromaDB HTTP client — tenant-scoped collections."""

from __future__ import annotations

import uuid

import chromadb
import structlog

from hospitai_agent.rag.profile import get_rag_profile

log = structlog.get_logger(__name__)

_client: chromadb.HttpClient | None = None


def reset_chroma_client() -> None:
    global _client
    _client = None


def get_chroma_client() -> chromadb.HttpClient:
    global _client
    if _client is None:
        profile = get_rag_profile()
        _client = chromadb.HttpClient(
            host=profile.chroma_host,
            port=profile.chroma_port,
        )
        log.info("chroma_connected", host=profile.chroma_host, port=profile.chroma_port)
    return _client


def tenant_collection_name(tenant_slug: str) -> str:
    prefix = get_rag_profile().chroma_collection_prefix
    return f"{prefix}_{tenant_slug}"


def get_tenant_collection(tenant_slug: str) -> chromadb.Collection:
    client = get_chroma_client()
    name = tenant_collection_name(tenant_slug)
    return client.get_or_create_collection(
        name=name,
        metadata={"hnsw:space": "cosine"},
    )


def delete_tenant_collection(tenant_slug: str) -> None:
    client = get_chroma_client()
    name = tenant_collection_name(tenant_slug)
    try:
        client.delete_collection(name)
        log.info("chroma_collection_deleted", collection=name)
    except Exception:
        log.warning("chroma_collection_delete_failed", collection=name)


def build_vector_id(document_id: uuid.UUID, chunk_index: int) -> str:
    return f"{document_id}_{chunk_index}"


def add_chunks_to_collection(
    tenant_slug: str,
    *,
    document_id: uuid.UUID,
    chunks: list[str],
    embeddings: list[list[float]],
    metadatas: list[dict] | None = None,
) -> list[str]:
    collection = get_tenant_collection(tenant_slug)
    ids = [build_vector_id(document_id, i) for i in range(len(chunks))]

    if metadatas is None:
        metadatas = [
            {"document_id": str(document_id), "chunk_index": i} for i in range(len(chunks))
        ]
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
    collection = get_tenant_collection(tenant_slug)
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
    collection = get_tenant_collection(tenant_slug)
    kwargs: dict = {
        "query_embeddings": [query_embedding],
        "n_results": min(n_results, 20),
    }
    if where:
        kwargs["where"] = where
    return collection.query(**kwargs)
