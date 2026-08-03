"""Remove consignment (کالای امانی) tracking entirely.

Product owner determined this feature was built incorrectly and wants it
fully gone — not just hidden in the UI. Removes the columns added in
20260729_01_consignment_purchase_items.py, mirroring how
20260801_01_remove_category_loyalty_multiplier.py handled the same kind of
full removal (drop via a new migration, leave the original add-migration
in place as history).

Data check before this migration: only 2 purchase_items rows in the dev
database ever had is_consignment=true, and both were already settled
(consignment_settled_at set) before this removal — settle_consignment_item()
permanently folds a line's value into Purchase.total/remaining_amount and
Supplier.balance at the moment it's settled, so those totals are already
correct and don't depend on this column existing. No unsettled rows existed,
so there is nothing to fold as part of this migration.

Revision ID: 20260804_01
Revises: 20260803_01
Create Date: 2026-08-04
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260804_01"
down_revision: str | None = "20260803_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("purchase_items") as batch_op:
        batch_op.drop_column("consignment_settled_at")
        batch_op.drop_column("is_consignment")


def downgrade() -> None:
    with op.batch_alter_table("purchase_items") as batch_op:
        batch_op.add_column(
            sa.Column("is_consignment", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch_op.add_column(
            sa.Column("consignment_settled_at", sa.DateTime(timezone=True), nullable=True)
        )
