"""Role sets shared by scheduling and support flows."""

from __future__ import annotations

from hospitai.infrastructure.db.models.enums import UserRole

BOOK_FOR_OTHERS_ROLES = frozenset(
    {
        UserRole.STAFF,
        UserRole.ADMIN,
        UserRole.DOCTOR,
        UserRole.OPERATOR,
    }
)
