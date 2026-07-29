"""Add manually-tracked status to check payment lines.

Revision ID: 20260727_02
Revises: 20260727_01
Create Date: 2026-07-27
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260727_02"
down_revision: str | None = "20260727_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("supplier_payments") as batch_op:
        batch_op.add_column(sa.Column("check_status", sa.String(length=8), nullable=True))
        batch_op.create_index("ix_supplier_payments_check_due_date", ["check_due_date"])
    op.execute(sa.text("UPDATE supplier_payments SET check_status = 'PENDING' WHERE method = 'CHECK'"))


def downgrade() -> None:
    with op.batch_alter_table("supplier_payments") as batch_op:
        batch_op.drop_index("ix_supplier_payments_check_due_date")
        batch_op.drop_column("check_status")
