"""external hospital connector columns on tenants

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-05-12

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c3d4e5f6a7b8"
down_revision: str | Sequence[str] | None = "b2c3d4e5f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column("external_hospital_base_url", sa.String(length=512), nullable=True),
    )
    op.add_column(
        "tenants",
        sa.Column("external_hospital_api_key", sa.String(length=512), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tenants", "external_hospital_api_key")
    op.drop_column("tenants", "external_hospital_base_url")
