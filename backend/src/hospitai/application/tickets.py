"""Support ticket creation and listing (tenant-scoped)."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from hospitai.application.errors import DomainError
from hospitai.application.permissions import BOOK_FOR_OTHERS_ROLES
from hospitai.infrastructure.db.models.enums import TicketPriority, TicketStatus
from hospitai.infrastructure.db.models.ticket import Ticket
from hospitai.infrastructure.db.models.user import User


def _new_ticket_reference() -> str:
    return f"TKT-{uuid.uuid4().hex[:20]}"


async def create_ticket(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    actor: User | None,
    subject: str,
    description: str,
    category: str | None,
    priority: TicketPriority,
) -> Ticket:
    reporter_user_id = actor.id if actor is not None else None
    ticket = Ticket(
        tenant_id=tenant_id,
        reference=_new_ticket_reference(),
        reporter_user_id=reporter_user_id,
        category=category,
        priority=priority,
        subject=subject.strip(),
        description=description.strip(),
        status=TicketStatus.OPEN,
    )
    session.add(ticket)
    await session.flush()
    await session.refresh(ticket)
    return ticket


async def get_ticket_by_reference(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    reference: str,
    actor: User | None,
) -> Ticket:
    stmt = select(Ticket).where(Ticket.tenant_id == tenant_id, Ticket.reference == reference)
    row = await session.execute(stmt)
    ticket = row.scalar_one_or_none()
    if ticket is None:
        raise DomainError("ticket_not_found", "Ticket not found", 404)
    if actor is not None:
        if actor.role not in BOOK_FOR_OTHERS_ROLES and ticket.reporter_user_id != actor.id:
            raise DomainError("forbidden", "You can only view your own tickets", status_code=403)
        return ticket
    if ticket.reporter_user_id is not None:
        raise DomainError(
            "forbidden",
            "Bu talebi görüntülemek için hesabınızla giriş yapmalısınız.",
            status_code=403,
        )
    return ticket


async def list_tickets(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    actor: User,
    status: TicketStatus | None,
    limit: int,
) -> list[Ticket]:
    stmt = select(Ticket).where(Ticket.tenant_id == tenant_id)
    if actor.role not in BOOK_FOR_OTHERS_ROLES:
        stmt = stmt.where(Ticket.reporter_user_id == actor.id)
    if status is not None:
        stmt = stmt.where(Ticket.status == status)
    stmt = stmt.order_by(Ticket.created_at.desc()).limit(min(limit, 100))
    result = await session.execute(stmt)
    return list(result.scalars().all())
