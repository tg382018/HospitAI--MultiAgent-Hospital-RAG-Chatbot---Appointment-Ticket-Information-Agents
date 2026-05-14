"""One-off process bootstrap for Celery workers (RAG / LLM profile from Settings)."""

from __future__ import annotations

from hospitai_agent.llm.profile import LLMProfile, configure_llm_profile
from hospitai_agent.rag.profile import RagInfrastructureProfile, configure_rag_profile

from hospitai.infrastructure.agent_tool_env import apply_optional_agent_env
from hospitai.infrastructure.settings import get_settings


def configure_worker_environment() -> None:
    """Mirror API lifespan RAG+LLM wiring so embeddings and Chroma calls work in workers."""
    settings = get_settings()
    apply_optional_agent_env(settings)
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
