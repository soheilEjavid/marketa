"""Add cashier shifts (till sessions) and link sales to them.

Revision ID: 20260728_01
Revises: 20260727_02
Create Date: 2026-07-28
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260728_01"
down_revision: str | None = "20260727_02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cashier_shifts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("cashier_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=6), nullable=False, server_default="open"),
        sa.Column("opening_cash", sa.Numeric(14, 2), nullable=False),
        sa.Column("closing_cash", sa.Numeric(14, 2), nullable=True),
        sa.Column("expected_cash", sa.Numeric(14, 2), nullable=True),
        sa.Column("difference", sa.Numeric(14, 2), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["cashier_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_cashier_shifts_cashier_id", "cashier_shifts", ["cashier_id"])
    op.create_index("ix_cashier_shifts_status", "cashier_shifts", ["status"])
    op.create_index("ix_cashier_shifts_opened_at", "cashier_shifts", ["opened_at"])

    with op.batch_alter_table("sales") as batch_op:
        batch_op.add_column(sa.Column("shift_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key("fk_sales_shift_id_cashier_shifts", "cashier_shifts", ["shift_id"], ["id"])
    op.create_index("ix_sales_shift_id", "sales", ["shift_id"])


def downgrade() -> None:
    op.drop_index("ix_sales_shift_id", table_name="sales")
    with op.batch_alter_table("sales") as batch_op:
        batch_op.drop_constraint("fk_sales_shift_id_cashier_shifts", type_="foreignkey")
        batch_op.drop_column("shift_id")

    op.drop_index("ix_cashier_shifts_opened_at", table_name="cashier_shifts")
    op.drop_index("ix_cashier_shifts_status", table_name="cashier_shifts")
    op.drop_index("ix_cashier_shifts_cashier_id", table_name="cashier_shifts")
    op.drop_table("cashier_shifts")
