"""String-backed enumerations stored in PostgreSQL as VARCHAR."""

from __future__ import annotations

from enum import StrEnum


def enum_values(enum_cls: type[StrEnum]) -> list[str]:
    """Persist StrEnum `.value` (lowercase) instead of member names."""
    return [m.value for m in enum_cls]


class UserRole(StrEnum):
    ADMIN = "admin"
    STAFF = "staff"
    DOCTOR = "doctor"
    PATIENT = "patient"
    OPERATOR = "operator"


class AppointmentStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    NO_SHOW = "no_show"
    BLOCKED = "blocked"  # admin-reserved, not bookable


class TicketPriority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TicketStatus(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"
