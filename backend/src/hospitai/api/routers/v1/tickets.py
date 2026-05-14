"""Ticket / complaint REST API."""

from __future__ import annotations

import json

import structlog
from fastapi import APIRouter, Query

from hospitai.api.deps import CurrentUser, SessionDep
from hospitai.api.http_mapping import raise_from_domain
from hospitai.api.schemas.tickets import CreateTicketRequest, TicketResponse
from hospitai.application.errors import DomainError
from hospitai.application.tickets import close_ticket, create_ticket, get_ticket_by_reference, list_tickets
from hospitai.infrastructure.db.models.enums import TicketStatus
from hospitai.workers.tasks import notify_domain_event

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/tickets", tags=["tickets"])


@router.get("", response_model=list[TicketResponse])
async def list_ticket_items(
    session: SessionDep,
    current: CurrentUser,
    status: TicketStatus | None = Query(default=None),
    limit: int = Query(50, ge=1, le=100),
) -> list[TicketResponse]:
    rows = await list_tickets(
        session,
        tenant_id=current.tenant_id,
        actor=current,
        status=status,
        limit=limit,
    )
    return [TicketResponse.model_validate(r) for r in rows]


@router.post("", response_model=TicketResponse, status_code=201)
async def create_ticket_item(
    session: SessionDep,
    current: CurrentUser,
    body: CreateTicketRequest,
) -> TicketResponse:
    try:
        ticket = await create_ticket(
            session,
            tenant_id=current.tenant_id,
            actor=current,
            subject=body.subject,
            description=body.description,
            category=body.category,
            priority=body.priority,
        )
        await session.commit()
    except DomainError as e:
        await session.rollback()
        raise_from_domain(e)
    try:
        notify_domain_event.delay(
            str(current.tenant_id),
            "ticket.created",
            json.dumps({"reference": ticket.reference, "reporter_id": str(current.id)}),
        )
    except Exception:
        log.warning("notify_enqueue_failed", exc_info=True)
    return TicketResponse.model_validate(ticket)


@router.patch("/{reference}/close", response_model=TicketResponse)
async def close_ticket_item(
    session: SessionDep,
    current: CurrentUser,
    reference: str,
) -> TicketResponse:
    try:
        ticket = await close_ticket(
            session,
            tenant_id=current.tenant_id,
            reference=reference,
            actor=current,
        )
        await session.commit()
    except DomainError as e:
        await session.rollback()
        raise_from_domain(e)
    return TicketResponse.model_validate(ticket)


@router.get("/{reference}", response_model=TicketResponse)
async def get_ticket_item(
    session: SessionDep,
    current: CurrentUser,
    reference: str,
) -> TicketResponse:
    try:
        ticket = await get_ticket_by_reference(
            session,
            tenant_id=current.tenant_id,
            reference=reference,
            actor=current,
        )
    except DomainError as e:
        raise_from_domain(e)
    return TicketResponse.model_validate(ticket)
