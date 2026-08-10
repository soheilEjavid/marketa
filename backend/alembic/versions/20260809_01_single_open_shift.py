"""Enforce "only one open shift" in the database, not just in Python.

services/shifts.py::open_shift() checks for an existing open shift and then
inserts, which is not atomic: two requests can both find nothing and both
insert. Nothing in the schema stopped the second one.

That invariant carries more weight than it looks. close_shift() cites it as
the reason its cash-out queries need no upper time bound, and those queries
(cash supplier payments, expenses, salaries, refunds) filter on a timestamp
alone with no shift column to narrow them. With two shifts open at once, one
cash expense is deducted from both reconciliations — each till then reports a
shortage for money that left the drawer once.

A partial unique index is the right shape here: any number of CLOSED rows,
at most one OPEN. Both SQLite and PostgreSQL support it.

The predicate compares against 'OPEN', not 'open'. SQLAlchemy's Enum type
persists the member *name*, so the stored string is uppercase; a predicate
written against ShiftStatus.OPEN.value would match nothing and leave the
table unconstrained while looking constrained.

Revision ID: 20260809_01
Revises: 20260805_01
"""

from alembic import op
import sqlalchemy as sa

revision = "20260809_01"
down_revision = "20260805_01"
branch_labels = None
depends_on = None

INDEX_NAME = "uq_cashier_shifts_single_open"


def upgrade() -> None:
    # A database that already carries more than one open shift would fail
    # the CREATE INDEX with a bare IntegrityError naming nothing useful.
    # Check first and say what to do about it.
    connection = op.get_bind()
    open_shifts = connection.execute(
        sa.text("SELECT COUNT(*) FROM cashier_shifts WHERE status = 'OPEN'")
    ).scalar_one()
    if open_shifts > 1:
        raise RuntimeError(
            f"Cannot add the single-open-shift constraint: {open_shifts} shifts are "
            "currently OPEN. Close all but one (the real, current till session) and "
            "run this migration again. Query them with: "
            "SELECT id, cashier_id, opened_at FROM cashier_shifts WHERE status = 'OPEN';"
        )

    op.create_index(
        INDEX_NAME,
        "cashier_shifts",
        ["status"],
        unique=True,
        sqlite_where=sa.text("status = 'OPEN'"),
        postgresql_where=sa.text("status = 'OPEN'"),
    )


def downgrade() -> None:
    op.drop_index(INDEX_NAME, table_name="cashier_shifts")
