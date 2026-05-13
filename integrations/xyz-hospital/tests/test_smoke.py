"""Smoke tests — FastAPI TestClient runs lifespan (creates SQLite schema + seed)."""

from __future__ import annotations

import os
from datetime import date

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("XYZ_DATABASE_URL", "sqlite+aiosqlite:////tmp/xyz_hospital_pytest.db")

from xyz_hospital.main import app  # noqa: E402


@pytest.fixture()
def client() -> TestClient:
    with TestClient(app) as c:
        yield c


def test_health(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_appointment_flow(client: TestClient) -> None:
    docs = client.get("/v1/doctors").json()
    assert len(docs) == 2

    day = date(2026, 5, 15)
    slots = client.get("/v1/slots", params={"doctor_code": "D1", "for_date": day.isoformat()}).json()
    assert len(slots) >= 1
    slot = slots[0]

    body = {
        "given_name": "Ali",
        "family_name": "Veli",
        "national_id": "10000000146",
        "department_code": "CARDIO",
        "doctor_code": "D1",
        "slot_start": slot["slot_start"],
        "slot_end": slot["slot_end"],
        "idempotency_key": "pytest-key-1",
    }
    r1 = client.post("/v1/appointments", json=body)
    assert r1.status_code == 200
    j1 = r1.json()
    assert j1["status"] == "accepted"
    assert j1.get("appointment_id")

    r2 = client.post("/v1/appointments", json=body)
    assert r2.json() == j1

    body2 = {**body, "idempotency_key": "pytest-key-2"}
    r3 = client.post("/v1/appointments", json=body2)
    assert r3.json()["status"] == "slot_full"
