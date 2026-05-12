"""Appointment REST API (tenant inferred from JWT)."""

from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Query

from hospitai.api.deps import CurrentUser, SessionDep
from hospitai.api.http_mapping import raise_from_domain
from hospitai.api.schemas.appointments import (
    AppointmentResponse,
    CreateAppointmentRequest,
    SlotWindow,
)
from hospitai.application.appointments import (
    cancel_appointment,
    create_appointment,
    list_appointments_for_actor,
    list_available_slots,
)
from hospitai.application.errors import DomainError

router = APIRouter(prefix="/appointments", tags=["appointments"])


@router.get("/available-slots", response_model=list[SlotWindow])
async def available_slots(
    session: SessionDep,
    current: CurrentUser,
    doctor_id: uuid.UUID = Query(..., description="Doctor UUID in this hospital"),
    day: date = Query(..., description="Calendar day (UTC date for clinic window)"),
    slot_minutes: int = Query(30, ge=10, le=120),
) -> list[SlotWindow]:
    try:
        slots = await list_available_slots(
            session,
            tenant_id=current.tenant_id,
            doctor_id=doctor_id,
            day=day,
            slot_minutes=slot_minutes,
        )
    except DomainError as e:
        raise_from_domain(e)
    return [SlotWindow(starts_at=s, ends_at=end) for s, end in slots]


@router.get("", response_model=list[AppointmentResponse])
async def list_appointments(
    session: SessionDep,
    current: CurrentUser,
    limit: int = Query(50, ge=1, le=100),
) -> list[AppointmentResponse]:
    rows = await list_appointments_for_actor(
        session,
        tenant_id=current.tenant_id,
        actor=current,
        limit=limit,
    )
    return [AppointmentResponse.model_validate(r) for r in rows]


@router.post("", response_model=AppointmentResponse, status_code=201)
async def create_appt(
    session: SessionDep,
    current: CurrentUser,
    body: CreateAppointmentRequest,
) -> AppointmentResponse:
    try:
        appt = await create_appointment(
            session,
            tenant_id=current.tenant_id,
            actor=current,
            doctor_id=body.doctor_id,
            starts_at=body.starts_at,
            ends_at=body.ends_at,
            department_id=body.department_id,
            notes=body.notes,
            patient_user_id=body.patient_user_id,
        )
        await session.commit()
    except DomainError as e:
        await session.rollback()
        raise_from_domain(e)
    return AppointmentResponse.model_validate(appt)


@router.post("/{appointment_id}/cancel", response_model=AppointmentResponse)
async def cancel_appt(
    session: SessionDep,
    current: CurrentUser,
    appointment_id: uuid.UUID,
) -> AppointmentResponse:
    try:
        appt = await cancel_appointment(
            session,
            tenant_id=current.tenant_id,
            appointment_id=appointment_id,
            actor=current,
        )
        await session.commit()
    except DomainError as e:
        await session.rollback()
        raise_from_domain(e)
    return AppointmentResponse.model_validate(appt)
