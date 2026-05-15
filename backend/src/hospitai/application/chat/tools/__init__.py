"""Chat workflow tools package.

Domain-specific tool modules:
- appointment_tools: list slots, list doctors, book, cancel
- ticket_tools:      create, list, get, close complaints
- rag_tools:         knowledge-base retrieval
- identity_tools:    patient identity verification
- common:            shared helpers (_get_tenant, _get_user, bridge helpers, etc.)
"""

from __future__ import annotations

from tools.contracts import ChatWorkflowTools

from .appointment_tools import (
    book_appointment_from_graph,
    cancel_appointment_from_graph,
    list_appointments_tool,
    list_available_slots_for_graph,
    list_doctors_tool,
)
from .identity_tools import verify_patient_identity_tool
from .rag_tools import hospital_info_tool, retrieve_knowledge_tool
from .ticket_tools import (
    close_ticket_tool,
    create_ticket_from_message_for_graph,
    create_ticket_tool,
    get_ticket_by_reference_for_graph,
    list_tickets_tool,
)

__all__ = [
    "make_workflow_tools",
    "list_available_slots_for_graph",
    "list_doctors_tool",
    "list_appointments_tool",
    "book_appointment_from_graph",
    "cancel_appointment_from_graph",
    "create_ticket_tool",
    "list_tickets_tool",
    "get_ticket_by_reference_for_graph",
    "create_ticket_from_message_for_graph",
    "close_ticket_tool",
    "retrieve_knowledge_tool",
    "hospital_info_tool",
    "verify_patient_identity_tool",
]


def make_workflow_tools() -> ChatWorkflowTools:
    """Bindings passed to `graph.configure_workflow_tools`."""
    return ChatWorkflowTools(
        list_doctors=list_doctors_tool,
        list_available_slots=list_available_slots_for_graph,
        list_user_appointments=list_appointments_tool,
        list_tickets=list_tickets_tool,
        get_ticket_by_reference=get_ticket_by_reference_for_graph,
        retrieve_knowledge=retrieve_knowledge_tool,
        create_ticket_from_message=create_ticket_from_message_for_graph,
        close_ticket=close_ticket_tool,
        verify_patient_identity=verify_patient_identity_tool,
        book_appointment=book_appointment_from_graph,
        cancel_appointment=cancel_appointment_from_graph,
    )
