"""Seed demo department, doctor, patient (TC), and one appointment for chat tests.

Revision ID: f2b3c4d5e6a7
Revises: f1a2b3c4d5e6
Create Date: 2026-05-12

LEGACY SEED MIGRATION — do not replicate this pattern.
Seed data should live in backend/scripts/seed_dev.py (idempotent, runnable at any time).
Schema changes belong in migrations; data seeding belongs in scripts.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "f2b3c4d5e6a7"
down_revision: str | Sequence[str] | None = "f1a2b3c4d5e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# demo-hospital tenant id from seed migration b2c3d4e5f6a7
TENANT = "00000001-0000-4000-8000-000000000001"
DEPT = "00000002-0000-4000-8000-000000000001"
DOCTOR = "00000003-0000-4000-8000-000000000001"
PATIENT = "00000004-0000-4000-8000-000000000001"
APPT = "00000005-0000-4000-8000-000000000001"


def upgrade() -> None:
    op.execute(
        f"""
        INSERT INTO departments (id, name, code, description, is_active, tenant_id, created_at, updated_at)
        SELECT '{DEPT}'::uuid, 'Dahiliye', 'DAH', 'Demo bölüm', true, '{TENANT}'::uuid, now(), now()
        WHERE NOT EXISTS (SELECT 1 FROM departments WHERE id = '{DEPT}'::uuid);

        INSERT INTO doctors (id, user_id, department_id, full_name, title, specialty, bio, photo_url, is_active, tenant_id, created_at, updated_at)
        SELECT '{DOCTOR}'::uuid, NULL, '{DEPT}'::uuid, 'Dr. Ayşe Yılmaz', 'Uzm. Dr.', 'Dahiliye', NULL, NULL, true, '{TENANT}'::uuid, now(), now()
        WHERE NOT EXISTS (SELECT 1 FROM doctors WHERE id = '{DOCTOR}'::uuid);

        INSERT INTO users (id, email, password_hash, full_name, national_id, role, is_active, tenant_id, created_at, updated_at)
        SELECT
            '{PATIENT}'::uuid,
            'ali.deniz.demo@demo-hospital.local',
            NULL,
            'Ali Deniz',
            '10000000146',
            'patient',
            true,
            '{TENANT}'::uuid,
            now(),
            now()
        WHERE NOT EXISTS (
            SELECT 1 FROM users WHERE tenant_id = '{TENANT}'::uuid AND national_id = '10000000146'
        );

        INSERT INTO appointments (
            id, patient_user_id, doctor_id, department_id, starts_at, ends_at, status, notes,
            guest_display_name, guest_contact, tenant_id, created_at, updated_at
        )
        SELECT
            '{APPT}'::uuid,
            '{PATIENT}'::uuid,
            '{DOCTOR}'::uuid,
            '{DEPT}'::uuid,
            '2026-12-15 10:00:00+00'::timestamptz,
            '2026-12-15 10:30:00+00'::timestamptz,
            'confirmed',
            'Demo randevu (TC doğrulama testi)',
            NULL,
            NULL,
            '{TENANT}'::uuid,
            now(),
            now()
        WHERE NOT EXISTS (SELECT 1 FROM appointments WHERE id = '{APPT}'::uuid);
        """
    )


def downgrade() -> None:
    op.execute(f"DELETE FROM appointments WHERE id = '{APPT}'::uuid;")
    op.execute(
        f"DELETE FROM users WHERE tenant_id = '{TENANT}'::uuid AND national_id = '10000000146';"
    )
    op.execute(f"DELETE FROM doctors WHERE id = '{DOCTOR}'::uuid;")
    op.execute(f"DELETE FROM departments WHERE id = '{DEPT}'::uuid;")
