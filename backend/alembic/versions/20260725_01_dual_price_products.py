"""Add dual-price fields to products and price_tier to sale_items.

Revision ID: 20260725_01
Revises: 20260723_01
Create Date: 2026-07-25
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260725_01"
down_revision: str | None = "20260723_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("products") as batch_op:
        batch_op.add_column(
            sa.Column("is_dual_priced", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch_op.add_column(sa.Column("old_purchase_price", sa.Numeric(14, 2), nullable=True))
        batch_op.add_column(sa.Column("old_sale_price", sa.Numeric(14, 2), nullable=True))
        batch_op.add_column(sa.Column("old_price_stock_estimate", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column("dual_price_started_at", sa.DateTime(timezone=True), nullable=True)
        )
    with op.batch_alter_table("sale_items") as batch_op:
        batch_op.add_column(sa.Column("price_tier", sa.String(length=10), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("sale_items") as batch_op:
        batch_op.drop_column("price_tier")
    with op.batch_alter_table("products") as batch_op:
        batch_op.drop_column("dual_price_started_at")
        batch_op.drop_column("old_price_stock_estimate")
        batch_op.drop_column("old_sale_price")
        batch_op.drop_column("old_purchase_price")
        batch_op.drop_column("is_dual_priced")
