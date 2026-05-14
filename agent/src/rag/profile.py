"""RAG / vector infrastructure injected by the platform backend at startup."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RagInfrastructureProfile:
    chroma_host: str
    chroma_port: int
    chroma_collection_prefix: str
    embedding_model: str
    embedding_api_key: str
    embedding_dimensions: int
    chunk_size: int
    chunk_overlap: int


_profile: RagInfrastructureProfile | None = None


def configure_rag_profile(profile: RagInfrastructureProfile) -> None:
    """Called from FastAPI lifespan with platform `Settings` RAG-related fields."""
    global _profile
    _profile = profile
    from rag.embeddings import reset_embedding_client
    from vectordb.chroma import reset_chroma_client

    reset_chroma_client()
    reset_embedding_client()


def get_rag_profile() -> RagInfrastructureProfile:
    if _profile is not None:
        return _profile
    raise RuntimeError(
        "RAG infrastructure is not configured. "
        "Call configure_rag_profile(...) during application startup."
    )
