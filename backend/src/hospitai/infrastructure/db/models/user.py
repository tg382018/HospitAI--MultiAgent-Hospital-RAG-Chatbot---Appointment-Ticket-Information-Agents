"""Users scoped to a tenant."""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Enum, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from hospitai.infrastructure.db.base import Base, TenantScopedMixin, TimestampMixin
from hospitai.infrastructure.db.models.enums import UserRole, enum_values


class User(Base, TenantScopedMixin, TimestampMixin):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("tenant_id", "email", name="uq_users_tenant_email"),
        UniqueConstraint("tenant_id", "national_id", name="uq_users_tenant_national_id"),
        UniqueConstraint("tenant_id", "phone", name="uq_users_tenant_phone"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    national_id: Mapped[str | None] = mapped_column(String(11), nullable=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, native_enum=False, length=32, values_callable=enum_values),
        nullable=False,
        index=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    tenant = relationship("Tenant", back_populates="users")
    doctor_profile = relationship(
        "Doctor",
        back_populates="user",
        uselist=False,
        foreign_keys="Doctor.user_id",
    )
    patient_appointments = relationship("Appointment", back_populates="patient_user")
    reported_tickets = relationship("Ticket", back_populates="reporter")
    conversations = relationship("Conversation", back_populates="user")
