"""Add sale_payment_lines for split cash/card/check payments on sales,
matching the existing purchase-side payment lines (supplier_payments).

Unlike supplier_payments, sale_id is NOT NULL here — there's no "standalone
sale payment" equivalent to a supplier balance settlement (that's
CustomerPayment with sale_id=None, untouched by this migration).

Revision ID: 20260802_01
Revises: 20260801_01
Create Date: 2026-08-02
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260802_01"
down_revision: str | None = "20260801_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

payment_method = sa.Enum("CASH", "CARD", "CREDIT", "MIXED", "CHECK", "LOYALTY", name="paymentmethod")


def upgrade() -> None:
    op.create_table(
        "sale_payment_lines",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("sale_id", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("method", payment_method, nullable=False),
        sa.Column("reference", sa.String(length=120), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("check_number", sa.String(length=60), nullable=True),
        sa.Column("check_bank_name", sa.String(length=120), nullable=True),
        sa.Column("check_due_date", sa.Date(), nullable=True),
        sa.Column("check_status", sa.String(length=8), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["sale_id"], ["sales.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("sale_id", "check_due_date", "paid_at"):
        op.create_index(f"ix_sale_payment_lines_{column}", "sale_payment_lines", [column])


def downgrade() -> None:
    op.drop_table("sale_payment_lines")
