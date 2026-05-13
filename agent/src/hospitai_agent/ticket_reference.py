"""Extract ticket reference codes from free text (tenant-scoped chat)."""

from __future__ import annotations

import re

# Matches platform references from ``tickets._new_ticket_reference``: TKT- + 20 hex chars
_TICKET_REF = re.compile(r"\b(TKT-)([a-fA-F0-9]{12,32})\b", re.IGNORECASE)


def extract_ticket_reference(text: str) -> str | None:
    """Return normalized reference (``TKT-`` + lowercase hex) or None."""
    m = _TICKET_REF.search(text or "")
    if not m:
        return None
    return f"TKT-{m.group(2).lower()}"
