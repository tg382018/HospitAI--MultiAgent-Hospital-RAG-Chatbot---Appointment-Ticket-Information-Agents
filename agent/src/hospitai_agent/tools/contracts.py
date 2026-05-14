"""Contracts for DB-backed tools supplied by the platform backend."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from hospitai_agent.state import ChatState

ListSlotsFn = Callable[[ChatState], Awaitable[dict[str, Any]]]
ListUserAppointmentsFn = Callable[[ChatState], Awaitable[dict[str, Any]]]
ListTicketsFn = Callable[[ChatState], Awaitable[dict[str, Any]]]
GetTicketByReferenceFn = Callable[[ChatState], Awaitable[dict[str, Any]]]
RetrieveFn = Callable[[ChatState, str], Awaitable[dict[str, Any]]]
CreateTicketFromMessageFn = Callable[[ChatState, str], Awaitable[dict[str, Any]]]
CloseTicketFn = Callable[[ChatState, str], Awaitable[dict[str, Any]]]
VerifyPatientIdentityFn = Callable[[ChatState], Awaitable[dict[str, Any]]]
BookAppointmentFn = Callable[[ChatState], Awaitable[dict[str, Any]]]
CancelAppointmentFn = Callable[[ChatState], Awaitable[dict[str, Any]]]


@dataclass(frozen=True, slots=True)
class ChatWorkflowTools:
    """Async callables implemented in `hospitai` (DB, RAG, appointments)."""

    list_available_slots: ListSlotsFn
    list_user_appointments: ListUserAppointmentsFn
    list_tickets: ListTicketsFn
    get_ticket_by_reference: GetTicketByReferenceFn
    retrieve_knowledge: RetrieveFn
    create_ticket_from_message: CreateTicketFromMessageFn
    close_ticket: CloseTicketFn
    verify_patient_identity: VerifyPatientIdentityFn
    book_appointment: BookAppointmentFn
    cancel_appointment: CancelAppointmentFn
