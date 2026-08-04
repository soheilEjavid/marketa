"""Widen payment-method columns for کارت به کارت (card_to_card)

SQLAlchemy sizes an Enum column to its longest member, so these columns were
created as VARCHAR(6)/VARCHAR(7). "card_to_card" is 12 characters and would
not fit.

SQLite ignores VARCHAR lengths entirely, so on the dev database this would
appear to work and only fail once the app is pointed at PostgreSQL — which
the README already advertises as supported. Widening them here keeps the two
backends honest with each other.

This also repairs a latent version of the same problem that predates this
change: `sales.payment_method` is VARCHAR(6), but PaymentMethod.LOYALTY
("loyalty") is 7 characters. That value has been assignable since the
loyalty program shipped and would already have failed on PostgreSQL; nobody
noticed because SQLite never complained.

Revision ID: 20260805_01
Revises: 20260804_01
"""

from alembic import op
import sqlalchemy as sa

revision = "20260805_01"
down_revision = "20260804_01"
branch_labels = None
depends_on = None

# Comfortably beyond the longest current member, so adding another tender
# type later does not need yet another migration.
WIDTH = 32

# (table, column, previous width) — previous widths are what SQLAlchemy's
# Enum() produced for the members that existed when each table was created.
COLUMNS = [
    ("sales", "payment_method", 6),
    ("sale_payment_lines", "method", 7),
    ("supplier_payments", "method", 6),
    ("customer_payments", "method", 6),
    ("payments", "method", 6),
]


def upgrade() -> None:
    for table, column, _ in COLUMNS:
        with op.batch_alter_table(table) as batch:
            batch.alter_column(
                column,
                existing_type=sa.String(),
                type_=sa.String(length=WIDTH),
                existing_nullable=False,
            )


def downgrade() -> None:
    # Narrowing back would truncate any card_to_card row, so the data has to
    # go first — a shop that recorded these tenders cannot simply roll back
    # and pretend they were something else.
    op.execute("DELETE FROM sale_payment_lines WHERE method = 'card_to_card'")
    op.execute("UPDATE sales SET payment_method = 'card' WHERE payment_method = 'card_to_card'")
    for table, column, previous in COLUMNS:
        with op.batch_alter_table(table) as batch:
            batch.alter_column(
                column,
                existing_type=sa.String(length=WIDTH),
                type_=sa.String(length=previous),
                existing_nullable=False,
            )
