"""Request / response schemas for the RAG document management API."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Ingest text (manual / FAQ)
# ---------------------------------------------------------------------------


class IngestTextRequest(BaseModel):
    title: str = Field(..., max_length=512, description="Human-readable document title")
    content: str = Field(..., min_length=1, description="Raw text content to ingest")
    source_type: str = Field(
        default="manual",
        max_length=64,
        description="Type identifier: manual, faq, policy, web",
    )
    extra_metadata: str | None = Field(
        default=None,
        description="Optional JSON-encoded metadata string",
    )


# ---------------------------------------------------------------------------
# Response
# ---------------------------------------------------------------------------


class DocumentResponse(BaseModel):
    id: uuid.UUID
    title: str
    source_type: str
    source_url: str | None = None
    file_path: str | None = None
    mime_type: str | None = None
    file_size_bytes: int | None = None
    status: str
    chunk_count: int
    error_message: str | None = None
    extra_metadata: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DocumentListResponse(BaseModel):
    documents: list[DocumentResponse]


# ---------------------------------------------------------------------------
# RAG retrieval
# ---------------------------------------------------------------------------


class RetrieveRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=4096, description="Search query")
    n_results: int = Field(default=5, ge=1, le=20, description="Max results to return")


class RetrievedChunk(BaseModel):
    content: str
    metadata: dict = Field(default_factory=dict)
    distance: float | None = None


class RetrieveResponse(BaseModel):
    query: str
    results: list[RetrievedChunk]