"""ChromaDB vector store — re-exports from chroma module."""

from vectordb.chroma import (
    add_chunks_to_collection,
    delete_document_vectors,
    delete_tenant_collection,
    get_chroma_client,
    get_tenant_collection,
    query_collection,
    reset_chroma_client,
    tenant_collection_name,
)

__all__ = [
    "add_chunks_to_collection",
    "delete_document_vectors",
    "delete_tenant_collection",
    "get_chroma_client",
    "get_tenant_collection",
    "query_collection",
    "reset_chroma_client",
    "tenant_collection_name",
]
