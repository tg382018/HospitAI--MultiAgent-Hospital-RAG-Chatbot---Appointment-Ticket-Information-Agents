"""Hospital (tenant) aggregate root."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import Boolean, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from hospitai.infrastructure.db.base import Base, TimestampMixin


class Tenant(Base, TimestampMixin):
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    branding: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    settings: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    external_hospital_base_url: Mapped[str | None] = mapped_column(
        String(512), nullable=True, doc="Base URL for external appointment API (e.g. xyz-hospital)."
    )
    external_hospital_api_key: Mapped[str | None] = mapped_column(
        String(512), nullable=True, doc="Optional Bearer token for external hospital API."
    )

    users = relationship("User", back_populates="tenant", cascade="all, delete-orphan")
    departments = relationship("Department", back_populates="tenant", cascade="all, delete-orphan")
    doctors = relationship("Doctor", back_populates="tenant", cascade="all, delete-orphan")
    appointments = relationship(
        "Appointment", back_populates="tenant", cascade="all, delete-orphan"
    )
    tickets = relationship("Ticket", back_populates="tenant", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="tenant", cascade="all, delete-orphan")
    conversations = relationship(
        "Conversation", back_populates="tenant", cascade="all, delete-orphan"
    )
