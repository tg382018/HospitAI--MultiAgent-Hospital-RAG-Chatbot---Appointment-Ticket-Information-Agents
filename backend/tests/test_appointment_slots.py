"""Pure scheduling slot math tests."""

from __future__ import annotations

from datetime import UTC, datetime

from hospitai.application.appointments import compute_free_slots, ranges_overlap


def test_ranges_overlap() -> None:
    a0 = datetime(2026, 5, 1, 10, 0, tzinfo=UTC)
    a1 = datetime(2026, 5, 1, 10, 30, tzinfo=UTC)
    b0 = datetime(2026, 5, 1, 10, 15, tzinfo=UTC)
    b1 = datetime(2026, 5, 1, 10, 45, tzinfo=UTC)
    assert ranges_overlap(a0, a1, b0, b1)


def test_ranges_disjoint() -> None:
    a0 = datetime(2026, 5, 1, 10, 0, tzinfo=UTC)
    a1 = datetime(2026, 5, 1, 10, 30, tzinfo=UTC)
    b0 = datetime(2026, 5, 1, 10, 30, tzinfo=UTC)
    b1 = datetime(2026, 5, 1, 11, 0, tzinfo=UTC)
    assert not ranges_overlap(a0, a1, b0, b1)


def test_compute_free_slots_respects_busy() -> None:
    ws = datetime(2026, 5, 1, 9, 0, tzinfo=UTC)
    we = datetime(2026, 5, 1, 10, 0, tzinfo=UTC)
    busy = [(datetime(2026, 5, 1, 9, 0, tzinfo=UTC), datetime(2026, 5, 1, 9, 30, tzinfo=UTC))]
    slots = compute_free_slots(ws, we, busy, slot_minutes=30)
    assert len(slots) == 1
    assert slots[0][0] == datetime(2026, 5, 1, 9, 30, tzinfo=UTC)
    assert slots[0][1] == datetime(2026, 5, 1, 10, 0, tzinfo=UTC)


def test_compute_free_slots_full_day_hour_steps() -> None:
    ws = datetime(2026, 5, 1, 9, 0, tzinfo=UTC)
    we = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    slots = compute_free_slots(ws, we, [], slot_minutes=60)
    assert len(slots) == 3
