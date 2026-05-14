"""RAG document tracking — stores metadata about ingested documents per tenant."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from hospitai.infrastructure.db.base import Base, TenantScopedMixin, TimestampMixin


class DocumentStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class Document(Base, TenantScopedMixin, TimestampMixin):
    """Tracks a single uploaded / ingested document for RAG per tenant."""

    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    source_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="pdf, docx, txt, faq, web, manual",
    )
    source_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    file_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=DocumentStatus.PENDING.value,
        index=True,
    )
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    extra_metadata: Mapped[str | None] = mapped_column(Text, nullable=True)

    tenant = relationship("Tenant")


class DocumentChunk(Base, TenantScopedMixin):
    """Individual chunk of a document stored in vector DB; this table is the SQL-side record."""

    __tablename__ = "document_chunks"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    vector_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="ID of the vector in ChromaDB",
    )

    document = relationship("Document", back_populates="chunks")
    tenant = relationship("Tenant")


Document.chunks = relationship(
    "DocumentChunk",
    back_populates="document",
    cascade="all, delete-orphan",
    order_by="DocumentChunk.chunk_index",
)
