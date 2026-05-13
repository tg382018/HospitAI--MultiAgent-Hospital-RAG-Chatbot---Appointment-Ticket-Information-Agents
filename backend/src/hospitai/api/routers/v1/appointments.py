"""Appointment REST API (tenant inferred from JWT)."""

from __future__ import annotations

import uuid
from datetime import date

import httpx
from fastapi import APIRouter, Query
from sqlalchemy import select

from hospitai.api.deps import CurrentUser, SessionDep
from hospitai.api.errors import AppError
from hospitai.api.http_mapping import raise_from_domain
from hospitai.api.schemas.appointments import (
    AppointmentResponse,
    CreateAppointmentRequest,
    ExternalAppointmentResultResponse,
    ExternalBookAppointmentRequest,
    SlotWindow,
)
from hospitai.application.appointments import (
    cancel_appointment,
    create_appointment,
    list_appointments_for_actor,
    list_available_slots,
)
from hospitai.application.errors import DomainError
from hospitai.infrastructure.db.models.tenant import Tenant
from hospitai.infrastructure.hospital_connector import (
    new_booking_idempotency_key,
    post_external_appointment,
)

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


@router.post(
    "/external-book",
    response_model=ExternalAppointmentResultResponse,
    summary="Book via external hospital connector",
)
async def book_external_via_connector(
    session: SessionDep,
    current: CurrentUser,
    body: ExternalBookAppointmentRequest,
) -> ExternalAppointmentResultResponse:
    """Proxies to the tenant's ``external_hospital_base_url`` (e.g. xyz-hospital)."""
    stmt = select(Tenant).where(Tenant.id == current.tenant_id)
    row = await session.execute(stmt)
    tenant = row.scalar_one_or_none()
    if tenant is None:
        raise AppError("tenant_not_found", "Hospital not found", status_code=404)
    base = (tenant.external_hospital_base_url or "").strip()
    if not base:
        raise AppError(
            "external_connector_not_configured",
            "This hospital is not configured for external appointment booking",
            status_code=400,
        )
    idem = body.idempotency_key or new_booking_idempotency_key()
    payload = {
        "given_name": body.given_name,
        "family_name": body.family_name,
        "national_id": body.national_id,
        "department_code": body.department_code,
        "doctor_code": body.doctor_code,
        "slot_start": body.slot_start.isoformat(),
        "slot_end": body.slot_end.isoformat(),
        "idempotency_key": idem,
        "contact_phone": body.contact_phone,
    }
    api_key = (tenant.external_hospital_api_key or "").strip() or None
    try:
        raw = await post_external_appointment(base_url=base, api_key=api_key, body=payload)
    except httpx.HTTPStatusError as e:
        raise AppError(
            "external_appointment_upstream",
            f"External hospital returned HTTP {e.response.status_code}",
            status_code=502,
        ) from e
    except httpx.RequestError as e:
        raise AppError(
            "external_appointment_unreachable",
            "Could not reach external hospital appointment API",
            status_code=502,
        ) from e
    return ExternalAppointmentResultResponse(
        status=str(raw.get("status", "error")),
        appointment_id=raw.get("appointment_id"),
        message=str(raw.get("message", "")),
    )


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
