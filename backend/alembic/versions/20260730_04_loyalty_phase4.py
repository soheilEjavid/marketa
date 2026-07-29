"""Loyalty program phase 4: category-level point override, tier-linked
earn-rate bonus.

Revision ID: 20260730_04
Revises: 20260730_03
Create Date: 2026-07-30
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260730_04"
down_revision: str | None = "20260730_03"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("categories") as batch_op:
        batch_op.add_column(sa.Column("loyalty_point_multiplier", sa.Numeric(6, 2), nullable=True))

    with op.batch_alter_table("loyalty_settings") as batch_op:
        batch_op.add_column(sa.Column("tier_silver_earn_bonus", sa.Numeric(4, 2), nullable=True))
        batch_op.add_column(sa.Column("tier_gold_earn_bonus", sa.Numeric(4, 2), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("loyalty_settings") as batch_op:
        batch_op.drop_column("tier_gold_earn_bonus")
        batch_op.drop_column("tier_silver_earn_bonus")

    with op.batch_alter_table("categories") as batch_op:
        batch_op.drop_column("loyalty_point_multiplier")
