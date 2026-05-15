"""Admin-only tenant settings and diagnostics."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from hospitai.api.deps import SessionDep, require_roles
from hospitai.api.http_mapping import raise_from_domain
from hospitai.api.schemas.admin_connector import (
    TenantConnectorProbeAccepted,
    TenantConnectorPublic,
    TenantConnectorUpdate,
)
from hospitai.api.schemas.admin_tenant import (
    AdminUserListResponse,
    AdminUserPatch,
    AdminUserPublic,
    TenantAgentLLMPublic,
    TenantPolicyPatch,
    TenantPolicyPublic,
)
from hospitai.api.schemas.chat_branding import ChatBrandingPatch, ChatBrandingPublic
from hospitai.application import appointments as appt_svc
from hospitai.application.errors import DomainError
from hospitai.application.tenant_admin import (
    admin_update_user,
    apply_agent_llm_settings_patch,
    get_tenant_for_admin,
    list_tenant_users,
    patch_tenant_branding,
    patch_tenant_policy,
)
from hospitai.application.tenant_branding import (
    CHAT_FAVICON_FILE_KEY,
    CHAT_HEADER_BACKGROUND_KEY,
    CHAT_LOGO_FILE_KEY,
    CHAT_QUICK_ACTIONS_KEY,
    CHAT_WELCOME_SUBTITLE_KEY,
    CHAT_WELCOME_TITLE_KEY,
    validate_header_background,
    validate_quick_actions,
    validate_welcome_text,
)
from hospitai.infrastructure.tenant_assets import (
    branding_public_response,
    delete_tenant_favicon,
    delete_tenant_logo,
    save_tenant_favicon,
    save_tenant_logo,
    validate_favicon_upload,
    validate_logo_upload,
)
from hospitai.application.tenant_agent_llm import (
    TenantAgentLLMPatch,
    tenant_agent_llm_public_fields,
)
from hospitai.application.tenant_policy import effective_policy
from hospitai.infrastructure.db.models.appointment import Appointment
from hospitai.infrastructure.db.models.clinical import Department, Doctor
from hospitai.infrastructure.db.models.enums import AppointmentStatus, UserRole
from hospitai.infrastructure.db.models.tenant import Tenant
from hospitai.infrastructure.db.models.user import User

_TZ_TURKEY = timezone(timedelta(hours=3))


async def _resolve_department_name_to_id(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    department_name: str | None,
) -> uuid.UUID | None:
    raw = (department_name or "").strip()
    if not raw:
        return None
    stmt = select(Department).where(Department.tenant_id == tenant_id, Department.name == raw)
    existing = (await session.execute(stmt)).scalar_one_or_none()
    if existing:
        return existing.id
    dept = Department(tenant_id=tenant_id, name=raw, is_active=True)
    session.add(dept)
    await session.flush()
    return dept.id


# ---- Pydantic schemas for doctor management --------------------------------


class DoctorCreate(BaseModel):
    full_name: str
    title: str | None = None
    department_name: str | None = None


class DoctorPatch(BaseModel):
    full_name: str | None = None
    title: str | None = None
    department_name: str | None = None
    is_active: bool | None = None


class BlockedSlotCreate(BaseModel):
    date: str   # ISO date YYYY-MM-DD
    time: str   # HH:MM in Turkey local time

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/ping")
async def admin_ping(
    _user: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
) -> dict[str, str]:
    return {"message": "ok", "scope": "admin"}


@router.get("/tenant-connector", response_model=TenantConnectorPublic)
async def get_tenant_connector(
    session: SessionDep,
    user: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
) -> TenantConnectorPublic:
    stmt = select(Tenant).where(Tenant.id == user.tenant_id)
    row = await session.execute(stmt)
    tenant = row.scalar_one_or_none()
    if tenant is None:
        return TenantConnectorPublic(
            external_hospital_base_url=None,
            has_external_hospital_api_key=False,
        )
    key = (tenant.external_hospital_api_key or "").strip()
    return TenantConnectorPublic(
        external_hospital_base_url=tenant.external_hospital_base_url,
        has_external_hospital_api_key=bool(key),
    )


@router.patch("/tenant-connector", response_model=TenantConnectorPublic)
async def patch_tenant_connector(
    session: SessionDep,
    current: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
    body: TenantConnectorUpdate,
) -> TenantConnectorPublic:
    stmt = select(Tenant).where(Tenant.id == current.tenant_id)
    row = await session.execute(stmt)
    tenant = row.scalar_one_or_none()
    if tenant is None:
        return TenantConnectorPublic(
            external_hospital_base_url=None,
            has_external_hospital_api_key=False,
        )
    patch = body.model_dump(exclude_unset=True)
    if "external_hospital_base_url" in patch:
        v = patch["external_hospital_base_url"]
        tenant.external_hospital_base_url = (v or "").strip() or None
    if "external_hospital_api_key" in patch:
        v = patch["external_hospital_api_key"]
        tenant.external_hospital_api_key = (v or "").strip() or None
    await session.commit()
    await session.refresh(tenant)
    key = (tenant.external_hospital_api_key or "").strip()
    return TenantConnectorPublic(
        external_hospital_base_url=tenant.external_hospital_base_url,
        has_external_hospital_api_key=bool(key),
    )


@router.post("/tenant-connector/probe", response_model=TenantConnectorProbeAccepted)
async def enqueue_external_connector_probe(
    user: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
) -> TenantConnectorProbeAccepted:
    """Dış HIS /v1/doctors erişimini Celery worker içinde dene (sohbeti bloklamaz)."""
    from hospitai.workers.tasks import probe_external_hospital_connectivity_task

    async_result = probe_external_hospital_connectivity_task.delay(str(user.tenant_id))
    return TenantConnectorProbeAccepted(task_id=async_result.id)


# ---- Tenant policy (JSONB flags) -------------------------------------------


@router.get("/tenant-policy", response_model=TenantPolicyPublic)
async def get_tenant_policy(
    session: SessionDep,
    user: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
) -> TenantPolicyPublic:
    tenant = await get_tenant_for_admin(session, tenant_id=user.tenant_id)
    pol = effective_policy(tenant)
    return TenantPolicyPublic(
        rag_retrieval_enabled=bool(pol.get("rag_retrieval_enabled", True)),
    )


@router.patch("/tenant-policy", response_model=TenantPolicyPublic)
async def patch_tenant_policy_endpoint(
    session: SessionDep,
    user: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
    body: TenantPolicyPatch,
) -> TenantPolicyPublic:
    tenant = await get_tenant_for_admin(session, tenant_id=user.tenant_id)
    patch = body.model_dump(exclude_unset=True)
    if not patch:
        pol = effective_policy(tenant)
        return TenantPolicyPublic(
            rag_retrieval_enabled=bool(pol.get("rag_retrieval_enabled", True)),
        )
    try:
        await patch_tenant_policy(session, tenant=tenant, policy_patch=patch)
        await session.commit()
        await session.refresh(tenant)
    except DomainError as e:
        await session.rollback()
        raise_from_domain(e)
    pol = effective_policy(tenant)
    return TenantPolicyPublic(
        rag_retrieval_enabled=bool(pol.get("rag_retrieval_enabled", True)),
    )


# ---- Tenant agent LLM (JSONB overrides) ------------------------------------


@router.get("/tenant-agent-llm", response_model=TenantAgentLLMPublic)
async def get_tenant_agent_llm(
    session: SessionDep,
    user: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
) -> TenantAgentLLMPublic:
    tenant = await get_tenant_for_admin(session, tenant_id=user.tenant_id)
    raw = tenant.settings if isinstance(tenant.settings, dict) else None
    return TenantAgentLLMPublic.model_validate(tenant_agent_llm_public_fields(raw))


@router.patch("/tenant-agent-llm", response_model=TenantAgentLLMPublic)
async def patch_tenant_agent_llm(
    session: SessionDep,
    user: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
    body: TenantAgentLLMPatch,
) -> TenantAgentLLMPublic:
    tenant = await get_tenant_for_admin(session, tenant_id=user.tenant_id)
    patch = body.model_dump(exclude_unset=True)
    if not patch:
        raw = tenant.settings if isinstance(tenant.settings, dict) else None
        return TenantAgentLLMPublic.model_validate(tenant_agent_llm_public_fields(raw))
    try:
        await apply_agent_llm_settings_patch(session, tenant=tenant, patch=patch)
        await session.commit()
        await session.refresh(tenant)
    except DomainError as e:
        await session.rollback()
        raise_from_domain(e)
    raw = tenant.settings if isinstance(tenant.settings, dict) else None
    return TenantAgentLLMPublic.model_validate(tenant_agent_llm_public_fields(raw))


# ---- Tenant users ----------------------------------------------------------


@router.get("/users", response_model=AdminUserListResponse)
async def list_admin_users(
    session: SessionDep,
    user: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
) -> AdminUserListResponse:
    rows = await list_tenant_users(session, tenant_id=user.tenant_id)
    return AdminUserListResponse(users=[AdminUserPublic.model_validate(u) for u in rows])


@router.patch("/users/{user_id}", response_model=AdminUserPublic)
async def patch_admin_user(
    session: SessionDep,
    user: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
    user_id: uuid.UUID,
    body: AdminUserPatch,
) -> AdminUserPublic:
    patch = body.model_dump(exclude_unset=True)
    if not patch:
        stmt = select(User).where(User.id == user_id, User.tenant_id == user.tenant_id)
        row = await session.execute(stmt)
        u = row.scalar_one_or_none()
        if u is None:
            raise_from_domain(DomainError("user_not_found", "User not found", status_code=404))
        return AdminUserPublic.model_validate(u)
    try:
        updated = await admin_update_user(
            session,
            tenant_id=user.tenant_id,
            actor=user,
            target_user_id=user_id,
            full_name=patch.get("full_name") if "full_name" in patch else None,
            role=patch.get("role") if "role" in patch else None,
            is_active=patch.get("is_active") if "is_active" in patch else None,
        )
        await session.commit()
        await session.refresh(updated)
    except DomainError as e:
        await session.rollback()
        raise_from_domain(e)
    return AdminUserPublic.model_validate(updated)


# ---- Chat UI branding ------------------------------------------------------


@router.get("/chat-branding", response_model=ChatBrandingPublic)
async def get_chat_branding(
    session: SessionDep,
    user: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
) -> ChatBrandingPublic:
    tenant = await get_tenant_for_admin(session, tenant_id=user.tenant_id)
    return ChatBrandingPublic.model_validate(branding_public_response(tenant))


@router.patch("/chat-branding", response_model=ChatBrandingPublic)
async def patch_chat_branding(
    session: SessionDep,
    user: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
    body: ChatBrandingPatch,
) -> ChatBrandingPublic:
    tenant = await get_tenant_for_admin(session, tenant_id=user.tenant_id)
    patch_raw = body.model_dump(exclude_unset=True)
    branding_patch: dict[str, object] = {}
    try:
        if "header_background" in patch_raw and patch_raw["header_background"] is not None:
            branding_patch[CHAT_HEADER_BACKGROUND_KEY] = validate_header_background(
                patch_raw["header_background"]
            )
        if "welcome_title" in patch_raw and patch_raw["welcome_title"] is not None:
            branding_patch[CHAT_WELCOME_TITLE_KEY] = validate_welcome_text(
                patch_raw["welcome_title"], field="welcome_title", max_len=200
            )
        if "welcome_subtitle" in patch_raw and patch_raw["welcome_subtitle"] is not None:
            branding_patch[CHAT_WELCOME_SUBTITLE_KEY] = validate_welcome_text(
                patch_raw["welcome_subtitle"], field="welcome_subtitle", max_len=500
            )
        if "quick_actions" in patch_raw and patch_raw["quick_actions"] is not None:
            branding_patch[CHAT_QUICK_ACTIONS_KEY] = validate_quick_actions(
                patch_raw["quick_actions"]
            )
        if branding_patch:
            await patch_tenant_branding(session, tenant=tenant, branding_patch=branding_patch)
            await session.commit()
            await session.refresh(tenant)
    except ValueError as e:
        await session.rollback()
        raise_from_domain(DomainError("validation_error", str(e), status_code=422))
    except DomainError as e:
        await session.rollback()
        raise_from_domain(e)
    return ChatBrandingPublic.model_validate(branding_public_response(tenant))


@router.post("/chat-branding/logo", response_model=ChatBrandingPublic)
async def upload_chat_logo(
    session: SessionDep,
    user: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
    logo: UploadFile = File(...),
) -> ChatBrandingPublic:
    tenant = await get_tenant_for_admin(session, tenant_id=user.tenant_id)
    data = await logo.read()
    try:
        ext = validate_logo_upload(
            filename=logo.filename,
            content_type=logo.content_type,
            size=len(data),
        )
        filename = save_tenant_logo(tenant, data=data, ext=ext)
        await patch_tenant_branding(
            session,
            tenant=tenant,
            branding_patch={CHAT_LOGO_FILE_KEY: filename},
        )
        await session.commit()
        await session.refresh(tenant)
    except ValueError as e:
        await session.rollback()
        raise_from_domain(DomainError("validation_error", str(e), status_code=422))
    except DomainError as e:
        await session.rollback()
        raise_from_domain(e)
    return ChatBrandingPublic.model_validate(branding_public_response(tenant))


@router.delete("/chat-branding/logo", response_model=ChatBrandingPublic)
async def delete_chat_logo(
    session: SessionDep,
    user: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
) -> ChatBrandingPublic:
    tenant = await get_tenant_for_admin(session, tenant_id=user.tenant_id)
    delete_tenant_logo(tenant)
    await patch_tenant_branding(
        session,
        tenant=tenant,
        branding_patch={CHAT_LOGO_FILE_KEY: None},
    )
    await session.commit()
    await session.refresh(tenant)
    return ChatBrandingPublic.model_validate(branding_public_response(tenant))


@router.post("/chat-branding/favicon", response_model=ChatBrandingPublic)
async def upload_chat_favicon(
    session: SessionDep,
    user: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
    favicon: UploadFile = File(...),
) -> ChatBrandingPublic:
    tenant = await get_tenant_for_admin(session, tenant_id=user.tenant_id)
    data = await favicon.read()
    try:
        validate_favicon_upload(
            filename=favicon.filename,
            content_type=favicon.content_type,
            size=len(data),
            data=data,
        )
        filename = save_tenant_favicon(tenant, data=data)
        await patch_tenant_branding(
            session,
            tenant=tenant,
            branding_patch={CHAT_FAVICON_FILE_KEY: filename},
        )
        await session.commit()
        await session.refresh(tenant)
    except ValueError as e:
        await session.rollback()
        raise_from_domain(DomainError("validation_error", str(e), status_code=422))
    except DomainError as e:
        await session.rollback()
        raise_from_domain(e)
    return ChatBrandingPublic.model_validate(branding_public_response(tenant))


@router.delete("/chat-branding/favicon", response_model=ChatBrandingPublic)
async def delete_chat_favicon(
    session: SessionDep,
    user: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
) -> ChatBrandingPublic:
    tenant = await get_tenant_for_admin(session, tenant_id=user.tenant_id)
    delete_tenant_favicon(tenant)
    await patch_tenant_branding(
        session,
        tenant=tenant,
        branding_patch={CHAT_FAVICON_FILE_KEY: None},
    )
    await session.commit()
    await session.refresh(tenant)
    return ChatBrandingPublic.model_validate(branding_public_response(tenant))


# ---- Tenant display name ---------------------------------------------------


@router.get("/tenant-name")
async def get_tenant_name(
    session: SessionDep,
    user: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
) -> dict[str, str]:
    """Return the current display name of the tenant."""
    stmt = select(Tenant.name, Tenant.slug).where(Tenant.id == user.tenant_id)
    row = (await session.execute(stmt)).first()
    if row is None:
        raise_from_domain(DomainError("tenant_not_found", "Tenant not found", status_code=404))
    return {"name": row.name, "slug": row.slug}


@router.patch("/tenant-name")
async def patch_tenant_name(
    session: SessionDep,
    user: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
    body: dict,
) -> dict[str, str]:
    """Update the display name of the tenant. Admin only."""
    new_name: str = (body.get("name") or "").strip()
    if not new_name:
        raise_from_domain(DomainError("validation_error", "name must not be empty", status_code=422))
    stmt = select(Tenant).where(Tenant.id == user.tenant_id)
    result = await session.execute(stmt)
    tenant = result.scalar_one_or_none()
    if tenant is None:
        raise_from_domain(DomainError("tenant_not_found", "Tenant not found", status_code=404))
    tenant.name = new_name
    await session.commit()
    await session.refresh(tenant)
    return {"name": tenant.name, "slug": tenant.slug}


# ---- Departments -----------------------------------------------------------


@router.get("/departments")
async def list_departments(
    session: SessionDep,
    user: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
) -> list[dict[str, Any]]:
    stmt = select(Department).where(Department.tenant_id == user.tenant_id).order_by(Department.name)
    rows = (await session.execute(stmt)).scalars().all()
    return [{"id": str(d.id), "name": d.name, "is_active": d.is_active} for d in rows]


# ---- Doctors CRUD ----------------------------------------------------------


@router.get("/doctors")
async def list_doctors(
    session: SessionDep,
    user: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
) -> list[dict[str, Any]]:
    stmt = (
        select(Doctor)
        .options(selectinload(Doctor.department))
        .where(Doctor.tenant_id == user.tenant_id)
        .order_by(Doctor.full_name)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [
        {
            "id": str(d.id),
            "full_name": d.full_name,
            "title": d.title,
            "specialty": d.specialty,
            "is_active": d.is_active,
            "department_id": str(d.department_id) if d.department_id else None,
            "department_name": d.department.name if d.department else None,
        }
        for d in rows
    ]


@router.post("/doctors", status_code=201)
async def create_doctor(
    session: SessionDep,
    user: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
    body: DoctorCreate,
) -> dict[str, Any]:
    full_name = (body.full_name or "").strip()
    if not full_name:
        raise_from_domain(DomainError("validation_error", "full_name required", status_code=422))
    dept_id = await _resolve_department_name_to_id(session, user.tenant_id, body.department_name)
    doc = Doctor(
        tenant_id=user.tenant_id,
        full_name=full_name,
        title=body.title,
        department_id=dept_id,
        is_active=True,
    )
    session.add(doc)
    await session.flush()
    await session.refresh(doc, ["department"])
    await session.commit()
    return {
        "id": str(doc.id),
        "full_name": doc.full_name,
        "title": doc.title,
        "specialty": doc.specialty,
        "is_active": doc.is_active,
        "department_id": str(doc.department_id) if doc.department_id else None,
        "department_name": doc.department.name if doc.department else None,
    }


@router.patch("/doctors/{doctor_id}")
async def update_doctor(
    session: SessionDep,
    user: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
    doctor_id: uuid.UUID,
    body: DoctorPatch,
) -> dict[str, Any]:
    stmt = (
        select(Doctor)
        .options(selectinload(Doctor.department))
        .where(Doctor.id == doctor_id, Doctor.tenant_id == user.tenant_id)
    )
    doc = (await session.execute(stmt)).scalar_one_or_none()
    if doc is None:
        raise_from_domain(DomainError("not_found", "Doctor not found", status_code=404))
    patch = body.model_dump(exclude_unset=True)
    if "full_name" in patch and patch["full_name"]:
        doc.full_name = patch["full_name"].strip()
    if "title" in patch:
        doc.title = patch["title"]
    if "is_active" in patch:
        doc.is_active = patch["is_active"]
    if "department_name" in patch:
        raw = patch["department_name"]
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            doc.department_id = None
        else:
            doc.department_id = await _resolve_department_name_to_id(
                session, user.tenant_id, raw if isinstance(raw, str) else None
            )
    await session.flush()
    await session.refresh(doc, ["department"])
    await session.commit()
    return {
        "id": str(doc.id),
        "full_name": doc.full_name,
        "title": doc.title,
        "specialty": doc.specialty,
        "is_active": doc.is_active,
        "department_id": str(doc.department_id) if doc.department_id else None,
        "department_name": doc.department.name if doc.department else None,
    }


@router.delete("/doctors/{doctor_id}", status_code=204)
async def delete_doctor(
    session: SessionDep,
    user: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
    doctor_id: uuid.UUID,
) -> None:
    stmt = select(Doctor).where(Doctor.id == doctor_id, Doctor.tenant_id == user.tenant_id)
    doc = (await session.execute(stmt)).scalar_one_or_none()
    if doc is None:
        raise_from_domain(DomainError("not_found", "Doctor not found", status_code=404))
    doc.is_active = False
    await session.commit()


# ---- Doctor slots (admin grid + blocked) -----------------------------------


@router.get("/doctors/{doctor_id}/day-slots")
async def doctor_day_slots(
    session: SessionDep,
    user: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
    doctor_id: uuid.UUID,
    day: str = Query(..., description="ISO date YYYY-MM-DD"),
) -> list[dict[str, Any]]:
    try:
        d = date.fromisoformat(day)
    except ValueError:
        raise_from_domain(DomainError("validation_error", "invalid date", status_code=422))
    try:
        return await appt_svc.admin_doctor_day_slots(
            session,
            tenant_id=user.tenant_id,
            doctor_id=doctor_id,
            day=d,
        )
    except DomainError as e:
        raise_from_domain(e)


@router.get("/doctors/{doctor_id}/blocked-slots")
async def list_blocked_slots(
    session: SessionDep,
    user: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
    doctor_id: uuid.UUID,
    day: str = Query(..., description="ISO date YYYY-MM-DD"),
) -> list[dict[str, Any]]:
    try:
        d = date.fromisoformat(day)
    except ValueError:
        raise_from_domain(DomainError("validation_error", "invalid date", status_code=422))
    day_start = datetime.combine(d, datetime.min.time(), tzinfo=_TZ_TURKEY)
    day_end = day_start + timedelta(days=1)
    stmt = select(Appointment).where(
        Appointment.tenant_id == user.tenant_id,
        Appointment.doctor_id == doctor_id,
        Appointment.status == AppointmentStatus.BLOCKED,
        Appointment.starts_at >= day_start,
        Appointment.starts_at < day_end,
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [
        {
            "id": str(r.id),
            "starts_at": r.starts_at.astimezone(_TZ_TURKEY).isoformat(),
            "ends_at": r.ends_at.astimezone(_TZ_TURKEY).isoformat(),
        }
        for r in rows
    ]


@router.post("/doctors/{doctor_id}/blocked-slots", status_code=201)
async def block_slot(
    session: SessionDep,
    user: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
    doctor_id: uuid.UUID,
    body: BlockedSlotCreate,
) -> dict[str, Any]:
    doc = (
        await session.execute(
            select(Doctor).where(Doctor.id == doctor_id, Doctor.tenant_id == user.tenant_id)
        )
    ).scalar_one_or_none()
    if doc is None:
        raise_from_domain(DomainError("not_found", "Doctor not found", status_code=404))
    try:
        d = date.fromisoformat(body.date)
        h, m = [int(x) for x in body.time.split(":")]
    except (ValueError, AttributeError):
        raise_from_domain(DomainError("validation_error", "invalid date or time", status_code=422))
    starts_at = datetime(d.year, d.month, d.day, h, m, 0, tzinfo=_TZ_TURKEY)
    ends_at = starts_at + timedelta(minutes=30)
    existing = (
        await session.execute(
            select(Appointment).where(
                Appointment.tenant_id == user.tenant_id,
                Appointment.doctor_id == doctor_id,
                Appointment.status == AppointmentStatus.BLOCKED,
                Appointment.starts_at == starts_at,
            )
        )
    ).scalar_one_or_none()
    if existing:
        return {
            "id": str(existing.id),
            "starts_at": existing.starts_at.astimezone(_TZ_TURKEY).isoformat(),
            "ends_at": existing.ends_at.astimezone(_TZ_TURKEY).isoformat(),
        }
    taken = (
        await session.execute(
            select(Appointment.id).where(
                Appointment.tenant_id == user.tenant_id,
                Appointment.doctor_id == doctor_id,
                Appointment.starts_at < ends_at,
                Appointment.ends_at > starts_at,
                Appointment.status.not_in(
                    [AppointmentStatus.CANCELLED, AppointmentStatus.BLOCKED]
                ),
            )
        )
    ).first()
    if taken is not None:
        raise_from_domain(
            DomainError(
                "slot_taken",
                "This slot already has a patient booking and cannot be blocked here.",
                status_code=409,
            )
        )
    appt = Appointment(
        tenant_id=user.tenant_id,
        doctor_id=doctor_id,
        department_id=doc.department_id,
        starts_at=starts_at,
        ends_at=ends_at,
        status=AppointmentStatus.BLOCKED,
        guest_display_name="[BLOCKED]",
    )
    session.add(appt)
    await session.commit()
    await session.refresh(appt)
    return {
        "id": str(appt.id),
        "starts_at": appt.starts_at.astimezone(_TZ_TURKEY).isoformat(),
        "ends_at": appt.ends_at.astimezone(_TZ_TURKEY).isoformat(),
    }


@router.delete("/doctors/{doctor_id}/blocked-slots/{slot_id}", status_code=204)
async def unblock_slot(
    session: SessionDep,
    user: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
    doctor_id: uuid.UUID,
    slot_id: uuid.UUID,
) -> None:
    stmt = select(Appointment).where(
        Appointment.id == slot_id,
        Appointment.tenant_id == user.tenant_id,
        Appointment.doctor_id == doctor_id,
        Appointment.status == AppointmentStatus.BLOCKED,
    )
    appt = (await session.execute(stmt)).scalar_one_or_none()
    if appt is None:
        raise_from_domain(DomainError("not_found", "Blocked slot not found", status_code=404))
    await session.delete(appt)
    await session.commit()
