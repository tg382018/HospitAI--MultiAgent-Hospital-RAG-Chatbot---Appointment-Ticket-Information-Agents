"""Appointment API schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SlotWindow(BaseModel):
    starts_at: datetime
    ends_at: datetime


class CreateAppointmentRequest(BaseModel):
    doctor_id: uuid.UUID
    starts_at: datetime
    ends_at: datetime
    department_id: uuid.UUID | None = None
    notes: str | None = Field(default=None, max_length=4000)
    patient_user_id: uuid.UUID | None = Field(
        default=None,
        description="Staff/doctor/admin: book for this user in the same hospital",
    )


class AppointmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    patient_user_id: uuid.UUID | None
    doctor_id: uuid.UUID
    department_id: uuid.UUID | None
    starts_at: datetime
    ends_at: datetime
    status: str
    notes: str | None
