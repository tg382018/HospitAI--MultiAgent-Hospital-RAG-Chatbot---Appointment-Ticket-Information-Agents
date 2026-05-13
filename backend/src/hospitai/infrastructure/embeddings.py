"""Embedding service — wraps OpenAI embedding API.

Provides both single-text and batch embedding operations.
Designed to be called synchronously from async context via asyncio.to_thread.
"""

from __future__ import annotations

import os

import structlog
from openai import OpenAI

from hospitai.infrastructure.settings import get_settings

log = structlog.get_logger(__name__)

_client: OpenAI | None = None


def _get_openai_client() -> OpenAI:
    """Lazy singleton OpenAI client."""
    global _client
    if _client is None:
        settings = get_settings()
        api_key = settings.embedding_api_key or os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            raise RuntimeError(
                "No embedding API key configured. "
                "Set EMBEDDING_API_KEY or OPENAI_API_KEY environment variable."
            )
        _client = OpenAI(api_key=api_key)
    return _client


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a list of texts using the configured embedding model.

    OpenAI supports batching up to ~2048 texts per request.
    We chunk into batches of 512 to be safe.
    """
    settings = get_settings()
    client = _get_openai_client()

    all_embeddings: list[list[float]] = []
    batch_size = 512

    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        response = client.embeddings.create(
            model=settings.embedding_model,
            input=batch,
            dimensions=settings.embedding_dimensions,
        )
        all_embeddings.extend([item.embedding for item in response.data])

    log.info("embeddings_created", count=len(texts), model=settings.embedding_model)
    return all_embeddings


def embed_single(text: str) -> list[float]:
    """Embed a single text string."""
    return embed_texts([text])[0]