"""Add optional Turkish national id (TC) on users for patient verification in chat.

Revision ID: f1a2b3c4d5e6
Revises: c3d4e5f6a7b8
Create Date: 2026-05-12

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f1a2b3c4d5e6"
down_revision: str | Sequence[str] | None = "c3d4e5f6a7b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("national_id", sa.String(length=11), nullable=True))
    op.create_index(op.f("ix_users_national_id"), "users", ["national_id"], unique=False)
    op.create_unique_constraint(
        "uq_users_tenant_national_id",
        "users",
        ["tenant_id", "national_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_users_tenant_national_id", "users", type_="unique")
    op.drop_index(op.f("ix_users_national_id"), table_name="users")
    op.drop_column("users", "national_id")
