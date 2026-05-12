"""Import ORM models so `Base.metadata` is fully populated."""

from __future__ import annotations

from hospitai.infrastructure.db.base import Base
from hospitai.infrastructure.db.models.appointment import Appointment
from hospitai.infrastructure.db.models.audit_log import AuditLog
from hospitai.infrastructure.db.models.clinical import Department, Doctor
from hospitai.infrastructure.db.models.conversation import Conversation, ConversationMessage
from hospitai.infrastructure.db.models.tenant import Tenant
from hospitai.infrastructure.db.models.ticket import Ticket
from hospitai.infrastructure.db.models.user import User

__all__ = [
    "Base",
    "Appointment",
    "AuditLog",
    "Conversation",
    "ConversationMessage",
    "Department",
    "Doctor",
    "Tenant",
    "Ticket",
    "User",
]
