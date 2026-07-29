"""Add optional selling price and expiry date to purchase items.

Revision ID: 20260723_01
Revises: 20260720_01
Create Date: 2026-07-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260723_01"
down_revision: str | None = "20260720_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("purchase_items") as batch_op:
        batch_op.add_column(
            sa.Column(
                "selling_price",
                sa.Numeric(14, 2),
                nullable=True,
            )
        )
        batch_op.add_column(sa.Column("expiry_date", sa.Date(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("purchase_items") as batch_op:
        batch_op.drop_column("expiry_date")
        batch_op.drop_column("selling_price")
