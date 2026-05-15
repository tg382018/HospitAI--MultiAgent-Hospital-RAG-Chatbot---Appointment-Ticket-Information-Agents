"""seed demo tenant for local dev / frontend

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-05-13

LEGACY SEED MIGRATION — do not replicate this pattern.
Seed data should live in backend/scripts/seed_dev.py (idempotent, runnable at any time).
Schema changes belong in migrations; data seeding belongs in scripts.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: str | Sequence[str] | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO tenants (id, name, slug, description, is_active, branding, settings, created_at, updated_at)
        SELECT
            '00000001-0000-4000-8000-000000000001'::uuid,
            'Demo Hospital',
            'demo-hospital',
            'Yerel geliştirme için varsayılan tenant (frontend + API).',
            true,
            NULL,
            NULL,
            now(),
            now()
        WHERE NOT EXISTS (SELECT 1 FROM tenants WHERE slug = 'demo-hospital');
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM tenants WHERE slug = 'demo-hospital'")
