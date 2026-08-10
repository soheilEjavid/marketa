"""Sell goods by weight (کالای وزنی).

Two changes, both about a quantity that is not a whole number.

`products.is_weighted` marks a product the till should ask for a weight
for — 2.350 kg of cheese — rather than stepping a whole-unit counter. The
quantity columns were already Numeric(14,3) and needed nothing; the gap
was that nothing recorded *which* products are sold that way. The existing
free-text `products.unit` stays exactly as it is and carries the label
(کیلوگرم / گرم); this flag carries the behaviour.

`products.old_price_stock_estimate` becomes Numeric(14,3). It was Integer,
which cannot hold "4.500 kg of the old batch left", and it is now drawn
down by the quantity actually sold rather than a flat 1 per invoice line.

Revision ID: 20260809_02
Revises: 20260809_01
"""

from alembic import op
import sqlalchemy as sa

revision = "20260809_02"
down_revision = "20260809_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column("is_weighted", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    # batch_alter_table: SQLite cannot ALTER a column type in place, so
    # Alembic rebuilds the table. No-op cost on PostgreSQL, which alters
    # Integer -> Numeric directly.
    with op.batch_alter_table("products") as batch:
        batch.alter_column(
            "old_price_stock_estimate",
            existing_type=sa.Integer(),
            type_=sa.Numeric(14, 3),
            existing_nullable=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("products") as batch:
        batch.alter_column(
            "old_price_stock_estimate",
            existing_type=sa.Numeric(14, 3),
            type_=sa.Integer(),
            existing_nullable=True,
        )
    op.drop_column("products", "is_weighted")
