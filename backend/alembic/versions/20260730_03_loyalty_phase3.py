"""Loyalty program phase 3: per-product point override, customer tiers,
and manager-triggered churn-recovery coupon issuance.

Revision ID: 20260730_03
Revises: 20260730_02
Create Date: 2026-07-30
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260730_03"
down_revision: str | None = "20260730_02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("products") as batch_op:
        batch_op.add_column(sa.Column("loyalty_point_multiplier", sa.Numeric(6, 2), nullable=True))

    with op.batch_alter_table("loyalty_settings") as batch_op:
        batch_op.add_column(sa.Column("tier_silver_min_spend", sa.Numeric(14, 2), nullable=True))
        batch_op.add_column(sa.Column("tier_gold_min_spend", sa.Numeric(14, 2), nullable=True))
        batch_op.add_column(sa.Column("churn_recovery_coupon_points", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("loyalty_settings") as batch_op:
        batch_op.drop_column("churn_recovery_coupon_points")
        batch_op.drop_column("tier_gold_min_spend")
        batch_op.drop_column("tier_silver_min_spend")

    with op.batch_alter_table("products") as batch_op:
        batch_op.drop_column("loyalty_point_multiplier")
