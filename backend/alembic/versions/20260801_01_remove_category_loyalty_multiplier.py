"""Remove category-level loyalty point override.

This was never part of the original loyalty points spec (points earn
solely from the margin-proportional/dead-stock calculation and the
per-product override) — category management should have nothing to do
with the loyalty program. Removes the column added in
20260730_04_loyalty_phase4.

Revision ID: 20260801_01
Revises: 20260731_01
Create Date: 2026-08-01
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260801_01"
down_revision: str | None = "20260731_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("categories") as batch_op:
        batch_op.drop_column("loyalty_point_multiplier")


def downgrade() -> None:
    with op.batch_alter_table("categories") as batch_op:
        batch_op.add_column(sa.Column("loyalty_point_multiplier", sa.Numeric(6, 2), nullable=True))
