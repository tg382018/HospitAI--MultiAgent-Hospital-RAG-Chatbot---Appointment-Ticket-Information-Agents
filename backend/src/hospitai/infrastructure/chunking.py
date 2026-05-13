"""Text chunking service for RAG document ingestion.

Uses tiktoken for token-accurate splitting. Chunks are designed to be
semantically meaningful and sized for embedding models.
"""

from __future__ import annotations

import re

import structlog
import tiktoken

from hospitai.infrastructure.settings import get_settings

log = structlog.get_logger(__name__)

_encoder: tiktoken.Encoding | None = None


def _get_encoder() -> tiktoken.Encoding:
    """Lazy-load tiktoken cl100k_base encoder (used by text-embedding-3-*)."""
    global _encoder
    if _encoder is None:
        _encoder = tiktoken.get_encoding("cl100k_base")
    return _encoder


def count_tokens(text: str) -> int:
    """Count the number of tokens in a text string."""
    enc = _get_encoder()
    return len(enc.encode(text))


def _split_into_paragraphs(text: str) -> list[str]:
    """Split text on double newlines (paragraph boundaries)."""
    paragraphs = re.split(r"\n\s*\n", text.strip())
    return [p.strip() for p in paragraphs if p.strip()]


def _split_into_sentences(text: str) -> list[str]:
    """Split text into sentences (handles common abbreviations)."""
    # Simple sentence splitting on period/question/exclamation followed by whitespace
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    return [s.strip() for s in sentences if s.strip()]


def chunk_text(
    text: str,
    *,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
) -> list[dict]:
    """Split text into token-bounded chunks with overlap.

    Strategy:
    1. Split into paragraphs
    2. If a paragraph is too large, split into sentences
    3. If a sentence is still too large, split by token count
    4. Merge small units up to chunk_size with overlap

    Returns a list of dicts: {"content": str, "token_count": int, "chunk_index": int}
    """
    settings = get_settings()
    max_tokens = chunk_size or settings.chunk_size
    overlap = chunk_overlap or settings.chunk_overlap
    enc = _get_encoder()

    # Phase 1: Break text into atomic units (paragraphs → sentences → forced splits)
    units: list[str] = []
    for para in _split_into_paragraphs(text):
        para_tokens = count_tokens(para)
        if para_tokens <= max_tokens:
            units.append(para)
        else:
            # Split paragraph into sentences
            for sentence in _split_into_sentences(para):
                sent_tokens = count_tokens(sentence)
                if sent_tokens <= max_tokens:
                    units.append(sentence)
                else:
                    # Force-split by tokens
                    token_ids = enc.encode(sentence)
                    start = 0
                    while start < len(token_ids):
                        end = min(start + max_tokens, len(token_ids))
                        chunk_str = enc.decode(token_ids[start:end])
                        units.append(chunk_str)
                        start = end

    # Phase 2: Merge units into chunks respecting token limits
    chunks: list[dict] = []
    current_parts: list[str] = []
    current_tokens = 0

    for unit in units:
        unit_tokens = count_tokens(unit)
        if current_tokens + unit_tokens > max_tokens and current_parts:
            # Flush current chunk
            content = "\n\n".join(current_parts)
            chunks.append({
                "content": content,
                "token_count": count_tokens(content),
                "chunk_index": len(chunks),
            })
            # Keep overlap: retain last parts that fit within overlap budget
            overlap_parts: list[str] = []
            overlap_tok = 0
            for p in reversed(current_parts):
                p_tok = count_tokens(p)
                if overlap_tok + p_tok > overlap:
                    break
                overlap_parts.insert(0, p)
                overlap_tok += p_tok
            current_parts = overlap_parts
            current_tokens = overlap_tok

        current_parts.append(unit)
        current_tokens += unit_tokens

    # Flush remaining
    if current_parts:
        content = "\n\n".join(current_parts)
        chunks.append({
            "content": content,
            "token_count": count_tokens(content),
            "chunk_index": len(chunks),
        })

    log.info(
        "text_chunked",
        total_chunks=len(chunks),
        max_tokens=max_tokens,
        overlap=overlap,
    )
    return chunks