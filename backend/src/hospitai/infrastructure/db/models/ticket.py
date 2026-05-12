"""Support tickets / complaints."""

from __future__ import annotations

import uuid

from sqlalchemy import Enum, ForeignKey, Index, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from hospitai.infrastructure.db.base import Base, TenantScopedMixin, TimestampMixin
from hospitai.infrastructure.db.models.enums import TicketPriority, TicketStatus, enum_values


class Ticket(Base, TenantScopedMixin, TimestampMixin):
    __tablename__ = "tickets"
    __table_args__ = (
        UniqueConstraint("tenant_id", "reference", name="uq_tickets_tenant_reference"),
        Index("ix_tickets_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    reference: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        doc="Human-facing stable id (e.g. nanoid) unique within tenant.",
    )
    reporter_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    category: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    priority: Mapped[TicketPriority] = mapped_column(
        Enum(TicketPriority, native_enum=False, length=32, values_callable=enum_values),
        nullable=False,
        server_default=TicketPriority.MEDIUM,
        index=True,
    )
    subject: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[TicketStatus] = mapped_column(
        Enum(TicketStatus, native_enum=False, length=32, values_callable=enum_values),
        nullable=False,
        server_default=TicketStatus.OPEN,
        index=True,
    )

    tenant = relationship("Tenant", back_populates="tickets")
    reporter = relationship("User", back_populates="reported_tickets")
