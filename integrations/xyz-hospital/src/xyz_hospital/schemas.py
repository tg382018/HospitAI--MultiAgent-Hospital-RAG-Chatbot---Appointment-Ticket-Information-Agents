"""Pydantic API contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

AppointmentStatus = Literal["accepted", "slot_full", "rejected", "error", "unavailable"]


class AppointmentCreate(BaseModel):
    given_name: str = Field(..., min_length=1, max_length=120)
    family_name: str = Field(..., min_length=1, max_length=120)
    national_id: str = Field(..., min_length=11, max_length=11, pattern=r"^\d{11}$")
    department_code: str = Field(..., min_length=1, max_length=64)
    doctor_code: str = Field(..., min_length=1, max_length=32)
    slot_start: datetime
    slot_end: datetime
    idempotency_key: str = Field(..., min_length=8, max_length=128)
    contact_phone: str | None = Field(default=None, max_length=32)


class AppointmentResult(BaseModel):
    status: AppointmentStatus
    appointment_id: str | None = None
    message: str = ""


class DoctorOut(BaseModel):
    code: str
    name: str
    department_code: str


class SlotOut(BaseModel):
    slot_start: datetime
    slot_end: datetime
    doctor_code: str
