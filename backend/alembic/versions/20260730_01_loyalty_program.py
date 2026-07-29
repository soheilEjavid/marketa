"""Add loyalty points program (باشگاه مشتریان): customer birth_date +
cached point balance, and an append-only loyalty_point_transactions ledger.

Revision ID: 20260730_01
Revises: 20260729_01
Create Date: 2026-07-30
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260730_01"
down_revision: str | None = "20260729_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("customers") as batch_op:
        batch_op.add_column(sa.Column("birth_date", sa.Date(), nullable=True))
        batch_op.add_column(
            sa.Column("loyalty_points_balance", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.add_column(
            sa.Column("loyalty_progress_toman", sa.Numeric(14, 2), nullable=False, server_default="0")
        )

    op.create_table(
        "loyalty_point_transactions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("points", sa.Integer(), nullable=False),
        sa.Column("transaction_type", sa.String(length=7), nullable=False),
        sa.Column("sale_id", sa.Integer(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expired", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"]),
        sa.ForeignKeyConstraint(["sale_id"], ["sales.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_loyalty_point_transactions_customer_id", "loyalty_point_transactions", ["customer_id"])
    op.create_index("ix_loyalty_point_transactions_sale_id", "loyalty_point_transactions", ["sale_id"])
    op.create_index("ix_loyalty_point_transactions_expires_at", "loyalty_point_transactions", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_loyalty_point_transactions_expires_at", table_name="loyalty_point_transactions")
    op.drop_index("ix_loyalty_point_transactions_sale_id", table_name="loyalty_point_transactions")
    op.drop_index("ix_loyalty_point_transactions_customer_id", table_name="loyalty_point_transactions")
    op.drop_table("loyalty_point_transactions")

    with op.batch_alter_table("customers") as batch_op:
        batch_op.drop_column("loyalty_progress_toman")
        batch_op.drop_column("loyalty_points_balance")
        batch_op.drop_column("birth_date")
