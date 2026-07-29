"""Loyalty program phase 2: manager-configurable auto-enrollment threshold.

Adds Customer.loyalty_member (grandfathering every existing customer to
True so behavior is unchanged until a manager actually sets a threshold)
and a single-row loyalty_settings table holding the two optional
threshold figures (invoice total / invoice profit).

Revision ID: 20260730_02
Revises: 20260730_01
Create Date: 2026-07-30
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260730_02"
down_revision: str | None = "20260730_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("customers") as batch_op:
        batch_op.add_column(
            sa.Column("loyalty_member", sa.Boolean(), nullable=False, server_default=sa.false())
        )
    op.execute("UPDATE customers SET loyalty_member = 1")

    op.create_table(
        "loyalty_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("min_invoice_total_for_membership", sa.Numeric(14, 2), nullable=True),
        sa.Column("min_invoice_profit_for_membership", sa.Numeric(14, 2), nullable=True),
        sa.Column("updated_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute(
        "INSERT INTO loyalty_settings (id, min_invoice_total_for_membership, "
        "min_invoice_profit_for_membership) VALUES (1, NULL, NULL)"
    )


def downgrade() -> None:
    op.drop_table("loyalty_settings")
    with op.batch_alter_table("customers") as batch_op:
        batch_op.drop_column("loyalty_member")
