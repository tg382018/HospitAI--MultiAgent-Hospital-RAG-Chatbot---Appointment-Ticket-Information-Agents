"""Add optional phone on users for guest patient verification (TR mobile).

Revision ID: h3i4j5k6l7m8
Revises: f2b3c4d5e6a7
Create Date: 2026-05-12

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "h3i4j5k6l7m8"
down_revision: str | Sequence[str] | None = "f2b3c4d5e6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TENANT = "00000001-0000-4000-8000-000000000001"


def upgrade() -> None:
    op.add_column("users", sa.Column("phone", sa.String(length=32), nullable=True))
    op.create_index(op.f("ix_users_phone"), "users", ["phone"], unique=False)
    op.create_unique_constraint("uq_users_tenant_phone", "users", ["tenant_id", "phone"])
    op.execute(
        f"""
        UPDATE users SET phone = '5551234567'
        WHERE tenant_id = '{TENANT}'::uuid AND national_id = '10000000146';
        """
    )


def downgrade() -> None:
    op.drop_constraint("uq_users_tenant_phone", "users", type_="unique")
    op.drop_index(op.f("ix_users_phone"), table_name="users")
    op.drop_column("users", "phone")
