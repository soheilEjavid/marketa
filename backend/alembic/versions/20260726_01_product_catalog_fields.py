"""Add SKU, pricing, unit, packaging, image and notes fields to products.

Revision ID: 20260726_01
Revises: 20260725_01
Create Date: 2026-07-26
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260726_01"
down_revision: str | None = "20260725_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("products") as batch_op:
        batch_op.add_column(sa.Column("sku", sa.String(length=60), nullable=True))
        batch_op.add_column(sa.Column("min_sale_price", sa.Numeric(14, 2), nullable=True))
        batch_op.add_column(sa.Column("unit", sa.String(length=30), nullable=True))
        batch_op.add_column(sa.Column("packaging_unit_label", sa.String(length=40), nullable=True))
        batch_op.add_column(sa.Column("packaging_unit_quantity", sa.Numeric(14, 3), nullable=True))
        batch_op.add_column(sa.Column("image_url", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("description", sa.Text(), nullable=True))
        batch_op.create_index("ix_products_sku", ["sku"], unique=True)


def downgrade() -> None:
    with op.batch_alter_table("products") as batch_op:
        batch_op.drop_index("ix_products_sku")
        batch_op.drop_column("description")
        batch_op.drop_column("image_url")
        batch_op.drop_column("packaging_unit_quantity")
        batch_op.drop_column("packaging_unit_label")
        batch_op.drop_column("unit")
        batch_op.drop_column("min_sale_price")
        batch_op.drop_column("sku")
