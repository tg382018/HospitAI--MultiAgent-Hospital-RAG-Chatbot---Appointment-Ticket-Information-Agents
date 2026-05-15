"""Tests for ticket reference extraction in chat."""

from __future__ import annotations

from tools.ticket_reference import extract_ticket_reference


def test_extract_ticket_reference_normalizes_hex() -> None:
    text = "Durum: TKT-ABCDEF01234567890123456 nedir?"
    assert extract_ticket_reference(text) == "TKT-abcdef01234567890123456"


def test_extract_ticket_reference_min_length() -> None:
    assert extract_ticket_reference("TKT-123456789012") == "TKT-123456789012"


def test_extract_ticket_reference_too_short() -> None:
    assert extract_ticket_reference("TKT-12345") is None


def test_extract_ticket_reference_absent() -> None:
    assert extract_ticket_reference("Randevu almak istiyorum") is None
