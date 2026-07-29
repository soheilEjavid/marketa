"""Extend customer and supplier party profiles.

Revision ID: 20260717_01
Revises: 20260716_02
Create Date: 2026-07-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260717_01"
down_revision: str | None = "20260716_02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("customers") as batch_op:
        batch_op.alter_column(
            "name",
            new_column_name="full_name",
            existing_type=sa.String(length=160),
            nullable=False,
        )
        batch_op.add_column(sa.Column("national_id", sa.String(length=20)))
        batch_op.add_column(
            sa.Column(
                "is_active",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            )
        )
        batch_op.create_index(
            "ix_customers_national_id", ["national_id"], unique=True
        )

    with op.batch_alter_table("suppliers") as batch_op:
        batch_op.add_column(
            sa.Column("contact_person", sa.String(length=120))
        )
        batch_op.add_column(
            sa.Column(
                "is_active",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("suppliers") as batch_op:
        batch_op.drop_column("is_active")
        batch_op.drop_column("contact_person")

    with op.batch_alter_table("customers") as batch_op:
        batch_op.drop_index("ix_customers_national_id")
        batch_op.drop_column("is_active")
        batch_op.drop_column("national_id")
        batch_op.alter_column(
            "full_name",
            new_column_name="name",
            existing_type=sa.String(length=160),
            nullable=False,
        )
