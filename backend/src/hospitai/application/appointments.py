"""Appointment scheduling rules (tenant-scoped)."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, time, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import select

from hospitai.application.errors import DomainError
from hospitai.application.permissions import BOOK_FOR_OTHERS_ROLES
from hospitai.infrastructure.db.models.appointment import Appointment
from hospitai.infrastructure.db.models.clinical import Doctor
from hospitai.infrastructure.db.models.enums import AppointmentStatus
from hospitai.infrastructure.db.models.user import User

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def utc_day_bounds(d: date) -> tuple[datetime, datetime]:
    start = datetime.combine(d, time.min, tzinfo=UTC)
    end = start + timedelta(days=1)
    return start, end


def default_clinic_hours(d: date) -> tuple[datetime, datetime]:
    """09:00–17:00 UTC on the given calendar day (MVP; later per-tenant TZ)."""
    day_start = datetime.combine(d, time.min, tzinfo=UTC)
    return (
        day_start + timedelta(hours=9),
        day_start + timedelta(hours=17),
    )


def ranges_overlap(a0: datetime, a1: datetime, b0: datetime, b1: datetime) -> bool:
    return a0 < b1 and b0 < a1


def compute_free_slots(
    work_start: datetime,
    work_end: datetime,
    busy: list[tuple[datetime, datetime]],
    *,
    slot_minutes: int = 30,
) -> list[tuple[datetime, datetime]]:
    step = timedelta(minutes=slot_minutes)
    slots: list[tuple[datetime, datetime]] = []
    cursor = work_start
    while cursor + step <= work_end:
        slot_end = cursor + step
        conflict = any(ranges_overlap(cursor, slot_end, b0, b1) for b0, b1 in busy)
        if not conflict:
            slots.append((cursor, slot_end))
        cursor = slot_end
    return slots


async def get_doctor_in_tenant(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    doctor_id: uuid.UUID,
) -> Doctor:
    stmt = select(Doctor).where(
        Doctor.tenant_id == tenant_id,
        Doctor.id == doctor_id,
        Doctor.is_active.is_(True),
    )
    row = await session.execute(stmt)
    doctor = row.scalar_one_or_none()
    if doctor is None:
        raise DomainError("doctor_not_found", "Doctor not found or inactive in this hospital", 404)
    return doctor


async def list_busy_intervals(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    doctor_id: uuid.UUID,
    window_start: datetime,
    window_end: datetime,
) -> list[tuple[datetime, datetime]]:
    stmt = select(Appointment.starts_at, Appointment.ends_at).where(
        Appointment.tenant_id == tenant_id,
        Appointment.doctor_id == doctor_id,
        Appointment.status != AppointmentStatus.CANCELLED,
        Appointment.starts_at < window_end,
        Appointment.ends_at > window_start,
    )
    result = await session.execute(stmt)
    return [(row[0], row[1]) for row in result.all()]


async def list_available_slots(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    doctor_id: uuid.UUID,
    day: date,
    slot_minutes: int = 30,
) -> list[tuple[datetime, datetime]]:
    await get_doctor_in_tenant(session, tenant_id=tenant_id, doctor_id=doctor_id)
    work_start, work_end = default_clinic_hours(day)
    day_start, day_end = utc_day_bounds(day)
    busy = await list_busy_intervals(
        session,
        tenant_id=tenant_id,
        doctor_id=doctor_id,
        window_start=day_start,
        window_end=day_end,
    )
    return compute_free_slots(work_start, work_end, busy, slot_minutes=slot_minutes)


async def _resolve_patient_user_id(
    *,
    actor: User,
    patient_user_id: uuid.UUID | None,
) -> uuid.UUID:
    if patient_user_id is None or patient_user_id == actor.id:
        return actor.id
    if actor.role not in BOOK_FOR_OTHERS_ROLES:
        raise DomainError(
            "forbidden",
            "Only staff can book appointments for another user",
            status_code=403,
        )
    return patient_user_id


async def ensure_patient_in_tenant(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    patient_user_id: uuid.UUID,
) -> None:
    stmt = select(User.id).where(
        User.tenant_id == tenant_id,
        User.id == patient_user_id,
        User.is_active.is_(True),
    )
    row = await session.execute(stmt)
    if row.scalar_one_or_none() is None:
        raise DomainError("patient_not_found", "Patient user not found in this hospital", 404)


async def create_appointment(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    actor: User,
    doctor_id: uuid.UUID,
    starts_at: datetime,
    ends_at: datetime,
    department_id: uuid.UUID | None,
    notes: str | None,
    patient_user_id: uuid.UUID | None,
) -> Appointment:
    if starts_at.tzinfo is None or ends_at.tzinfo is None:
        raise DomainError("invalid_time", "starts_at and ends_at must be timezone-aware (UTC)", 400)
    if ends_at <= starts_at:
        raise DomainError("invalid_range", "ends_at must be after starts_at", 400)

    await get_doctor_in_tenant(session, tenant_id=tenant_id, doctor_id=doctor_id)

    if department_id is not None:
        from hospitai.infrastructure.db.models.clinical import Department

        dstmt = select(Department.id).where(
            Department.tenant_id == tenant_id,
            Department.id == department_id,
            Department.is_active.is_(True),
        )
        drow = await session.execute(dstmt)
        if drow.scalar_one_or_none() is None:
            raise DomainError("department_not_found", "Department not found in this hospital", 404)

    patient_id = await _resolve_patient_user_id(actor=actor, patient_user_id=patient_user_id)
    await ensure_patient_in_tenant(session, tenant_id=tenant_id, patient_user_id=patient_id)

    overlap = await session.execute(
        select(Appointment.id).where(
            Appointment.tenant_id == tenant_id,
            Appointment.doctor_id == doctor_id,
            Appointment.status != AppointmentStatus.CANCELLED,
            Appointment.starts_at < ends_at,
            Appointment.ends_at > starts_at,
        )
    )
    if overlap.scalar_one_or_none() is not None:
        raise DomainError("slot_unavailable", "This time overlaps an existing appointment", 409)

    appt = Appointment(
        tenant_id=tenant_id,
        patient_user_id=patient_id,
        doctor_id=doctor_id,
        department_id=department_id,
        starts_at=starts_at,
        ends_at=ends_at,
        status=AppointmentStatus.CONFIRMED,
        notes=notes,
    )
    session.add(appt)
    await session.flush()
    await session.refresh(appt)
    return appt


async def get_appointment_in_tenant(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    appointment_id: uuid.UUID,
) -> Appointment:
    stmt = select(Appointment).where(
        Appointment.tenant_id == tenant_id,
        Appointment.id == appointment_id,
    )
    row = await session.execute(stmt)
    appt = row.scalar_one_or_none()
    if appt is None:
        raise DomainError("appointment_not_found", "Appointment not found", 404)
    return appt


async def cancel_appointment(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    appointment_id: uuid.UUID,
    actor: User,
) -> Appointment:
    appt = await get_appointment_in_tenant(
        session,
        tenant_id=tenant_id,
        appointment_id=appointment_id,
    )
    if appt.status == AppointmentStatus.CANCELLED:
        return appt

    can_manage_others = actor.role in BOOK_FOR_OTHERS_ROLES
    if not can_manage_others and appt.patient_user_id != actor.id:
        raise DomainError("forbidden", "You can only cancel your own appointments", status_code=403)

    appt.status = AppointmentStatus.CANCELLED
    await session.flush()
    await session.refresh(appt)
    return appt


async def list_appointments_for_actor(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    actor: User,
    limit: int = 50,
) -> list[Appointment]:
    stmt = select(Appointment).where(Appointment.tenant_id == tenant_id)
    if actor.role not in BOOK_FOR_OTHERS_ROLES:
        stmt = stmt.where(Appointment.patient_user_id == actor.id)
    stmt = stmt.order_by(Appointment.starts_at.desc()).limit(min(limit, 100))
    result = await session.execute(stmt)
    return list(result.scalars().all())
