"""Published slot grid and validation (Europe/Istanbul business hours)."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Istanbul")

MORNING = (time(9, 0), time(12, 0))
AFTERNOON = (time(13, 0), time(17, 0))
STEP = timedelta(minutes=30)


def _day_bounds(d: date) -> tuple[datetime, datetime]:
    start_local = datetime.combine(d, time.min, tzinfo=TZ)
    end_local = start_local + timedelta(days=1)
    return start_local.astimezone(UTC), end_local.astimezone(UTC)


def iter_published_slots(for_date: date) -> list[tuple[datetime, datetime]]:
    """Return UTC slot_start, slot_end pairs for one calendar day in Istanbul."""
    d = for_date
    windows: list[tuple[time, time]] = [MORNING, AFTERNOON]
    out: list[tuple[datetime, datetime]] = []
    for start_t, end_t in windows:
        cursor = datetime.combine(d, start_t, tzinfo=TZ).astimezone(UTC)
        end_dt = datetime.combine(d, end_t, tzinfo=TZ).astimezone(UTC)
        while cursor + STEP <= end_dt:
            nxt = cursor + STEP
            out.append((cursor, nxt))
            cursor = nxt
    return out


def slot_matches_publication(slot_start: datetime, slot_end: datetime, doctor_code: str) -> bool:
    """True if slot aligns with a published 30m window (doctor_code reserved for future per-doctor hours)."""
    _ = doctor_code
    if slot_start.tzinfo is None:
        slot_start = slot_start.replace(tzinfo=UTC)
    if slot_end.tzinfo is None:
        slot_end = slot_end.replace(tzinfo=UTC)
    day = slot_start.astimezone(TZ).date()
    for a, b in iter_published_slots(day):
        if a == slot_start and b == slot_end:
            return True
    return False


def turkish_national_id_valid(tc: str) -> bool:
    """Official TC algorithm; rejects obviously invalid IDs with clear rejection path."""
    if len(tc) != 11 or not tc.isdigit():
        return False
    digits = [int(c) for c in tc]
    if digits[0] == 0:
        return False
    s1 = sum(digits[i] for i in range(0, 9, 2))
    s2 = sum(digits[i] for i in range(1, 9, 2))
    d10 = (s1 * 7 - s2) % 10
    if digits[9] != d10:
        return False
    if sum(digits[:10]) % 10 != digits[10]:
        return False
    return True
