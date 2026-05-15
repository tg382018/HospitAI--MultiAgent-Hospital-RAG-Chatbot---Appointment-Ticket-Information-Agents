"""Tests for slot listing date validation (no default-to-today, reject past)."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

from hospitai.application.chat.tools.appointment_tools import _parse_slot_list_day


def test_parse_slot_list_day_empty_requires_date() -> None:
    day, outcome, msg = _parse_slot_list_day("")
    assert day is None
    assert outcome == "date_required"
    assert msg and "tarih" in (msg.lower())


def test_parse_slot_list_day_whitespace_requires_date() -> None:
    day, outcome, _msg = _parse_slot_list_day("   ")
    assert day is None
    assert outcome == "date_required"


@patch(
    "hospitai.application.chat.tools.appointment_tools.today_in_turkey",
    return_value=date(2026, 5, 15),
)
def test_parse_slot_list_day_rejects_past_iso(_mock: object) -> None:
    day, outcome, msg = _parse_slot_list_day("2026-05-10")
    assert day is None
    assert outcome == "past_date"
    assert msg and "geçmiş" in msg.lower()


@patch(
    "hospitai.application.chat.tools.appointment_tools.today_in_turkey",
    return_value=date(2026, 5, 15),
)
def test_parse_slot_list_day_today_and_tomorrow(_mock: object) -> None:
    d0, o0, _ = _parse_slot_list_day("bugün")
    assert o0 is None and d0 == date(2026, 5, 15)
    d1, o1, _ = _parse_slot_list_day("yarın")
    assert o1 is None and d1 == date(2026, 5, 16)


@patch(
    "hospitai.application.chat.tools.appointment_tools.today_in_turkey",
    return_value=date(2026, 5, 15),
)
def test_parse_slot_list_day_future_iso_ok(_mock: object) -> None:
    d, o, _ = _parse_slot_list_day("2026-05-20")
    assert o is None and d == date(2026, 5, 20)


def test_parse_slot_list_day_invalid_format() -> None:
    with patch(
        "hospitai.application.chat.tools.appointment_tools.today_in_turkey",
        return_value=date(2026, 5, 15),
    ):
        day, outcome, msg = _parse_slot_list_day("15/05/2026")
    assert day is None
    assert outcome == "invalid_date"
    assert "YYYY" in msg or "ör" in msg.lower()
