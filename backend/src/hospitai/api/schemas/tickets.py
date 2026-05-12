"""Ticket API schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from hospitai.infrastructure.db.models.enums import TicketPriority


class CreateTicketRequest(BaseModel):
    subject: str = Field(..., min_length=1, max_length=512)
    description: str = Field(..., min_length=1, max_length=20000)
    category: str | None = Field(default=None, max_length=128)
    priority: TicketPriority = TicketPriority.MEDIUM


class TicketResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    reference: str
    reporter_user_id: uuid.UUID | None
    category: str | None
    priority: str
    subject: str
    description: str
    status: str
    created_at: datetime
    updated_at: datetime
