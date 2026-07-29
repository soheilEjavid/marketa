"""Loyalty program: configurable rolling window for tier spend.

Revision ID: 20260731_01
Revises: 20260730_04
Create Date: 2026-07-31
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260731_01"
down_revision: str | None = "20260730_04"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("loyalty_settings") as batch_op:
        batch_op.add_column(sa.Column("tier_window_days", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("loyalty_settings") as batch_op:
        batch_op.drop_column("tier_window_days")
