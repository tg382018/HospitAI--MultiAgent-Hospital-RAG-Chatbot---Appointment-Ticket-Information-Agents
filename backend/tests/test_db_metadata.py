"""ORM metadata smoke test (no database required)."""

from __future__ import annotations

import hospitai.infrastructure.db.models as models


def test_all_expected_tables_registered() -> None:
    names = set(models.Base.metadata.tables.keys())
    expected = {
        "appointments",
        "audit_logs",
        "conversation_messages",
        "conversations",
        "departments",
        "doctors",
        "tenants",
        "tickets",
        "users",
    }
    assert expected <= names
