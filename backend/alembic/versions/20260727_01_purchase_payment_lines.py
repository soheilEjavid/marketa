"""Support multi-line/split payments on purchases (cash + check, etc).

Adds check-specific fields to supplier_payments and makes supplier_id
nullable there, since a purchase's payment lines must be recorded even
when the purchase has no supplier on file.

Revision ID: 20260727_01
Revises: 20260726_01
Create Date: 2026-07-27
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260727_01"
down_revision: str | None = "20260726_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("supplier_payments") as batch_op:
        batch_op.alter_column("supplier_id", existing_type=sa.Integer(), nullable=True)
        batch_op.add_column(sa.Column("check_number", sa.String(length=60), nullable=True))
        batch_op.add_column(sa.Column("check_bank_name", sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column("check_due_date", sa.Date(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("supplier_payments") as batch_op:
        batch_op.drop_column("check_due_date")
        batch_op.drop_column("check_bank_name")
        batch_op.drop_column("check_number")
        batch_op.alter_column("supplier_id", existing_type=sa.Integer(), nullable=False)
