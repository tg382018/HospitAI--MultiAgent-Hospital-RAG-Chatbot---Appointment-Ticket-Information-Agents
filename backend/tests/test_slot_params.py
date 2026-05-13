"""Tests for agent-side slot query hint extraction (used by chat tools)."""

from __future__ import annotations

from datetime import date, timedelta

from hospitai_agent.slot_params import extract_slot_query_params


def test_extract_iso_date_overrides_relative() -> None:
    p = extract_slot_query_params("yarın değil 2026-06-01 için Dr. Ali müsait mi")
    assert p["target_date"] == "2026-06-01"


def test_extract_yarin() -> None:
    p = extract_slot_query_params("Yarın kardiyoloji müsait saat")
    assert p["target_date"] == (date.today() + timedelta(days=1)).isoformat()
    assert "kardiyo" in p["department_name"].lower() or p["department_name"] == "Kardiyoloji"


def test_extract_doctor_prefix() -> None:
    p = extract_slot_query_params("doktor Ayşe için slot")
    assert "ayşe" in p["doctor_name"].lower()
