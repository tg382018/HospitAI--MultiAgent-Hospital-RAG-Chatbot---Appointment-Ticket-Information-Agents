"""Tests for slot tool user-facing summaries."""

from __future__ import annotations

from datetime import date

from hospitai.application.chat.slot_tool_result import (
    user_message_external_catalog_empty,
    user_message_no_matching_doctors_external,
    user_message_slots_found,
    wrap_slot_tool_success,
)


def test_wrap_slots_found_includes_date_and_bullets() -> None:
    day = date(2026, 6, 1)
    slots = [
        {"doctor": "Dr. A", "department": "CARDIO", "start": "10:00", "end": "10:30"},
    ]
    r = wrap_slot_tool_success(
        day=day,
        source="internal",
        serialized_slots=slots,
        ext_meta=None,
        filter_department="",
        filter_doctor="",
    )
    assert r["success"] is True
    assert r["slot_outcome"] == "slots_found"
    assert r["count"] == 1
    assert "2026-06-01" in r["user_message_tr"]
    assert "Dr. A" in r["user_message_tr"]


def test_wrap_external_no_match_when_filter_and_zero_selected() -> None:
    day = date(2026, 6, 2)
    r = wrap_slot_tool_success(
        day=day,
        source="external",
        serialized_slots=[],
        ext_meta={"matched_doctors": 0, "filter_applied": True, "upstream_doctor_count": 5},
        filter_department="nöro",
        filter_doctor="",
    )
    assert r["slot_outcome"] == "no_matching_doctors_external"
    expected = user_message_no_matching_doctors_external(date_iso=day.isoformat())
    assert expected == r["user_message_tr"]


def test_wrap_external_catalog_empty() -> None:
    day = date(2026, 6, 3)
    r = wrap_slot_tool_success(
        day=day,
        source="external",
        serialized_slots=[],
        ext_meta={"matched_doctors": 0, "filter_applied": False, "upstream_doctor_count": 0},
        filter_department="",
        filter_doctor="",
    )
    assert r["slot_outcome"] == "external_catalog_empty"
    assert r["user_message_tr"] == user_message_external_catalog_empty(date_iso=day.isoformat())


def test_user_message_slots_found_external_prefix() -> None:
    s = user_message_slots_found(
        date_iso="2026-01-05",
        source="external",
        slots=[{"doctor": "X", "department": "Y", "start": "a", "end": "b"}],
    )
    assert "dış hastane" in s.lower()
    assert "2026-01-05" in s
