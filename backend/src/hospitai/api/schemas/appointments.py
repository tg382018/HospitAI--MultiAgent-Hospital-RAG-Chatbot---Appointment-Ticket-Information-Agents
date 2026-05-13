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


class ExternalBookAppointmentRequest(BaseModel):
    """Forwarded to the tenant external hospital API (xyz-hospital POST /v1/appointments)."""

    given_name: str = Field(..., min_length=1, max_length=120)
    family_name: str = Field(..., min_length=1, max_length=120)
    national_id: str = Field(..., min_length=11, max_length=11, pattern=r"^\d{11}$")
    department_code: str = Field(..., min_length=1, max_length=64)
    doctor_code: str = Field(..., min_length=1, max_length=32)
    slot_start: datetime
    slot_end: datetime
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=128)
    contact_phone: str | None = Field(default=None, max_length=32)


class ExternalAppointmentResultResponse(BaseModel):
    status: str
    appointment_id: str | None = None
    message: str = ""
