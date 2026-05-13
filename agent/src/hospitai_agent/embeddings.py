"""OpenAI embedding calls (sync; use asyncio.to_thread from the backend)."""

from __future__ import annotations

import os

import structlog
from openai import OpenAI

from hospitai_agent.rag_profile import get_rag_profile

log = structlog.get_logger(__name__)

_client: OpenAI | None = None


def reset_embedding_client() -> None:
    global _client
    _client = None


def _get_openai_client() -> OpenAI:
    global _client
    if _client is None:
        profile = get_rag_profile()
        api_key = profile.embedding_api_key or os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            raise RuntimeError(
                "No embedding API key configured. "
                "Set EMBEDDING_API_KEY or OPENAI_API_KEY environment variable."
            )
        _client = OpenAI(api_key=api_key)
    return _client


def embed_texts(texts: list[str]) -> list[list[float]]:
    profile = get_rag_profile()
    client = _get_openai_client()

    all_embeddings: list[list[float]] = []
    batch_size = 512

    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        response = client.embeddings.create(
            model=profile.embedding_model,
            input=batch,
            dimensions=profile.embedding_dimensions,
        )
        all_embeddings.extend([item.embedding for item in response.data])

    log.info("embeddings_created", count=len(texts), model=profile.embedding_model)
    return all_embeddings


def embed_single(text: str) -> list[float]:
    return embed_texts([text])[0]
