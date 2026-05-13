"""FastAPI application."""

from __future__ import annotations

import json
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from pathlib import Path

import structlog
from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from xyz_hospital.config import get_settings
from xyz_hospital.database import get_engine, get_session_factory
from xyz_hospital.models import Appointment, Base, Doctor, IdempotentResponse
from xyz_hospital.schemas import AppointmentCreate, AppointmentResult, DoctorOut, SlotOut
from xyz_hospital.slots import _day_bounds, iter_published_slots, slot_matches_publication, turkish_national_id_valid

log = structlog.get_logger(__name__)


async def _seed_doctors(session: AsyncSession) -> None:
    result = await session.execute(select(Doctor).limit(1))
    if result.scalar_one_or_none() is not None:
        return
    docs = [
        Doctor(
            id=uuid.UUID("00000000-0000-4000-8000-000000000001"),
            code="D1",
            name="Dr. Ayşe Kaya",
            department_code="CARDIO",
        ),
        Doctor(
            id=uuid.UUID("00000000-0000-4000-8000-000000000002"),
            code="D2",
            name="Dr. Mehmet Öz",
            department_code="NEURO",
        ),
    ]
    session.add_all(docs)
    await session.commit()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = get_settings()
    url = settings.database_url
    if ":///./" in url or "://./" in url:
        Path("data").mkdir(parents=True, exist_ok=True)
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with get_session_factory()() as session:
        await _seed_doctors(session)
    log.info("xyz_hospital_startup", database_url=url.split("@")[-1])
    yield
    await engine.dispose()


app = FastAPI(title="XYZ Hospital API", version="0.0.1", lifespan=lifespan)


async def session_dep() -> AsyncSession:
    factory = get_session_factory()
    async with factory() as session:
        yield session


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "xyz-hospital"}


@app.get("/v1/doctors", response_model=list[DoctorOut])
async def list_doctors(session: AsyncSession = Depends(session_dep)) -> list[DoctorOut]:
    result = await session.execute(select(Doctor).where(Doctor.is_active.is_(True)).order_by(Doctor.code))
    rows = result.scalars().all()
    return [DoctorOut(code=r.code, name=r.name, department_code=r.department_code) for r in rows]


@app.get("/v1/slots", response_model=list[SlotOut])
async def list_slots(
    doctor_code: str,
    for_date: date,
    session: AsyncSession = Depends(session_dep),
) -> list[SlotOut]:
    doc_result = await session.execute(select(Doctor).where(Doctor.code == doctor_code))
    doctor = doc_result.scalar_one_or_none()
    if doctor is None:
        raise HTTPException(status_code=404, detail="unknown_doctor_code")

    day_start, day_end = _day_bounds(for_date)
    booked_result = await session.execute(
        select(Appointment.slot_start).where(
            Appointment.doctor_id == doctor.id,
            Appointment.slot_start >= day_start,
            Appointment.slot_start < day_end,
        )
    )
    taken = {r[0] for r in booked_result.all()}

    return [
        SlotOut(slot_start=start, slot_end=end, doctor_code=doctor_code)
        for start, end in iter_published_slots(for_date)
        if start not in taken
    ]


async def _store_idempotent(session: AsyncSession, key: str, res: AppointmentResult) -> None:
    session.add(
        IdempotentResponse(
            idempotency_key=key,
            body_json=json.dumps(res.model_dump()),
            created_at=datetime.now(UTC),
        )
    )


@app.post("/v1/appointments", response_model=AppointmentResult)
async def create_appointment(
    body: AppointmentCreate,
    session: AsyncSession = Depends(session_dep),
) -> AppointmentResult:
    settings = get_settings()
    if not settings.hospital_available:
        return AppointmentResult(
            status="unavailable",
            message="Hastane randevu sistemi geçici olarak kapalı. Lütfen daha sonra tekrar deneyin.",
        )

    cached = await session.get(IdempotentResponse, body.idempotency_key)
    if cached is not None:
        return AppointmentResult(**json.loads(cached.body_json))

    doc_result = await session.execute(select(Doctor).where(Doctor.code == body.doctor_code))
    doctor = doc_result.scalar_one_or_none()
    if doctor is None:
        res = AppointmentResult(status="rejected", message="Geçersiz doktor kodu.")
        await _store_idempotent(session, body.idempotency_key, res)
        await session.commit()
        return res

    if body.department_code.upper() != doctor.department_code.upper():
        res = AppointmentResult(
            status="rejected",
            message="Seçilen bölüm ile doktor bölümü uyuşmuyor.",
        )
        await _store_idempotent(session, body.idempotency_key, res)
        await session.commit()
        return res

    if body.slot_end <= body.slot_start:
        res = AppointmentResult(status="rejected", message="slot_end, slot_start'tan sonra olmalıdır.")
        await _store_idempotent(session, body.idempotency_key, res)
        await session.commit()
        return res

    if not slot_matches_publication(body.slot_start, body.slot_end, body.doctor_code):
        res = AppointmentResult(
            status="rejected",
            message="Bu zaman dilimi yayınlanan slotlar arasında değil.",
        )
        await _store_idempotent(session, body.idempotency_key, res)
        await session.commit()
        return res

    if not turkish_national_id_valid(body.national_id):
        res = AppointmentResult(status="rejected", message="Geçersiz T.C. kimlik numarası.")
        await _store_idempotent(session, body.idempotency_key, res)
        await session.commit()
        return res

    doctor_id = doctor.id

    appt = Appointment(
        id=uuid.uuid4(),
        idempotency_key=body.idempotency_key,
        given_name=body.given_name,
        family_name=body.family_name,
        national_id=body.national_id,
        department_code=body.department_code.upper(),
        doctor_id=doctor_id,
        slot_start=body.slot_start,
        slot_end=body.slot_end,
        created_at=datetime.now(UTC),
    )
    session.add(appt)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        async with get_session_factory()() as s2:
            cached2 = await s2.get(IdempotentResponse, body.idempotency_key)
            if cached2 is not None:
                return AppointmentResult(**json.loads(cached2.body_json))
            row = (
                await s2.execute(
                    select(Appointment).where(
                        Appointment.doctor_id == doctor_id,
                        Appointment.slot_start == body.slot_start,
                    )
                )
            ).scalar_one_or_none()
            if row is not None:
                res = AppointmentResult(
                    status="slot_full",
                    message="Bu saat için kontenjan dolu. Lütfen başka bir slot seçin.",
                )
                await _store_idempotent(s2, body.idempotency_key, res)
                await s2.commit()
                return res
            res = AppointmentResult(status="error", message="Randevu kaydı oluşturulamadı (çakışma).")
            await _store_idempotent(s2, body.idempotency_key, res)
            await s2.commit()
            return res

    res = AppointmentResult(
        status="accepted",
        appointment_id=str(appt.id),
        message="Randevunuz oluşturuldu.",
    )
    await _store_idempotent(session, body.idempotency_key, res)
    await session.commit()
    return res
