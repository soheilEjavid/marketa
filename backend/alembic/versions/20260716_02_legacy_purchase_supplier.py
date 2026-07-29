"""Allow purchases without a supplier for legacy development databases.

Revision ID: 20260716_02
Revises: 20260716_01
Create Date: 2026-07-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260716_02"
down_revision: str | None = "20260716_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("purchases") as batch_op:
        batch_op.alter_column(
            "supplier_id",
            existing_type=sa.Integer(),
            nullable=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("purchases") as batch_op:
        batch_op.alter_column(
            "supplier_id",
            existing_type=sa.Integer(),
            nullable=False,
        )
