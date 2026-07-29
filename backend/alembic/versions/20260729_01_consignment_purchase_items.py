"""Add consignment (کالای امانی) tracking to purchase items.

Revision ID: 20260729_01
Revises: 20260728_01
Create Date: 2026-07-29
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260729_01"
down_revision: str | None = "20260728_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("purchase_items") as batch_op:
        batch_op.add_column(
            sa.Column("is_consignment", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch_op.add_column(
            sa.Column("consignment_settled_at", sa.DateTime(timezone=True), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("purchase_items") as batch_op:
        batch_op.drop_column("consignment_settled_at")
        batch_op.drop_column("is_consignment")
