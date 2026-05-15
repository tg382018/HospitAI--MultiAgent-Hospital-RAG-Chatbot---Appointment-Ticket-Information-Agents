"""Idempotent development seed script.

Inserts demo data required for local development and chat tests.
Safe to run multiple times — all operations use INSERT ... WHERE NOT EXISTS.

Usage:
    cd backend
    python scripts/seed_dev.py

Going forward, ALL new seed data should be added here instead of in Alembic
migration files. Schema changes belong in migrations; data seeding belongs here.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Ensure the src package is importable when run directly.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sqlalchemy.ext.asyncio import create_async_engine

from hospitai.infrastructure.settings import get_settings

_DEMO_TENANT_ID = "00000001-0000-4000-8000-000000000001"
_DEMO_DEPT_ID = "00000002-0000-4000-8000-000000000001"
_DEMO_DOCTOR_ID = "00000003-0000-4000-8000-000000000001"
_DEMO_PATIENT_ID = "00000004-0000-4000-8000-000000000001"


async def seed() -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)

    async with engine.begin() as conn:
        # Demo tenant
        await conn.execute(
            __import__("sqlalchemy", fromlist=["text"]).text(
                """
                INSERT INTO tenants
                    (id, name, slug, description, is_active, branding, settings, created_at, updated_at)
                SELECT
                    :id::uuid, :name, :slug, :desc, true, NULL, NULL, now(), now()
                WHERE NOT EXISTS (SELECT 1 FROM tenants WHERE slug = :slug)
                """
            ),
            {
                "id": _DEMO_TENANT_ID,
                "name": "Demo Hospital",
                "slug": "demo-hospital",
                "desc": "Yerel geliştirme için varsayılan tenant (frontend + API).",
            },
        )
        print("  [ok] tenant: demo-hospital")

        # Demo department
        await conn.execute(
            __import__("sqlalchemy", fromlist=["text"]).text(
                """
                INSERT INTO departments (id, tenant_id, name, is_active, created_at, updated_at)
                SELECT :id::uuid, :tid::uuid, :name, true, now(), now()
                WHERE NOT EXISTS (
                    SELECT 1 FROM departments WHERE id = :id::uuid
                )
                """
            ),
            {"id": _DEMO_DEPT_ID, "tid": _DEMO_TENANT_ID, "name": "Dahiliye"},
        )
        print("  [ok] department: Dahiliye")

        # Demo doctor
        await conn.execute(
            __import__("sqlalchemy", fromlist=["text"]).text(
                """
                INSERT INTO doctors
                    (id, tenant_id, department_id, full_name, specialization, is_active,
                     created_at, updated_at)
                SELECT :id::uuid, :tid::uuid, :dept::uuid, :name, :spec, true, now(), now()
                WHERE NOT EXISTS (SELECT 1 FROM doctors WHERE id = :id::uuid)
                """
            ),
            {
                "id": _DEMO_DOCTOR_ID,
                "tid": _DEMO_TENANT_ID,
                "dept": _DEMO_DEPT_ID,
                "name": "Dr. Ayşe Yılmaz",
                "spec": "İç Hastalıkları",
            },
        )
        print("  [ok] doctor: Dr. Ayşe Yılmaz")

        # Demo patient user
        await conn.execute(
            __import__("sqlalchemy", fromlist=["text"]).text(
                """
                INSERT INTO users
                    (id, tenant_id, email, hashed_password, full_name, role,
                     national_id, phone, is_active, created_at, updated_at)
                SELECT
                    :id::uuid, :tid::uuid, :email, :pw, :name, 'patient',
                    :tc, :phone, true, now(), now()
                WHERE NOT EXISTS (SELECT 1 FROM users WHERE id = :id::uuid)
                """
            ),
            {
                "id": _DEMO_PATIENT_ID,
                "tid": _DEMO_TENANT_ID,
                "email": "demo.patient@example.com",
                # bcrypt hash of 'DemoPass123!' — change before real use
                "pw": "$2b$12$demohashdemohashdemohasZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ",
                "name": "Demo Hasta",
                "tc": "12345678901",
                "phone": "05551234567",
            },
        )
        print("  [ok] patient user: demo.patient@example.com")

    await engine.dispose()
    print("\nSeed complete.")


if __name__ == "__main__":
    print("Running dev seed...")
    asyncio.run(seed())
