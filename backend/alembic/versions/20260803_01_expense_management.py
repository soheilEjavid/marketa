"""Add expense management: expenses, salary_payments, salary_advances.

Purely additive — no existing table (sales, purchases, products, users) is
touched. See docs/expense-management.md.

`expenses.category` is a plain string, not a foreign key to `categories`:
that table is product-specific (globally-unique name, back-populated only
from Product), and reusing it here would let an expense category collide
with a product category of the same name.

`salary_payments` carries a unique (employee_id, period_year, period_month)
constraint — a deliberate safety addition beyond the feature doc's literal
spec, since a duplicate payment row for the same employee/month would
silently double-count in net_profit().

Revision ID: 20260803_01
Revises: 20260802_01
Create Date: 2026-08-03
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260803_01"
down_revision: str | None = "20260802_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

expense_payment_method = sa.Enum("CASH", "BANK", name="expensepaymentmethod")


def upgrade() -> None:
    expense_payment_method.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "expenses",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_recurring", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("payment_method", expense_payment_method, nullable=False),
        sa.Column("receipt_image_url", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_expenses_category", "expenses", ["category"])
    op.create_index("ix_expenses_date", "expenses", ["date"])

    op.create_table(
        "salary_payments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("employee_id", sa.Integer(), nullable=False),
        sa.Column("period_month", sa.Integer(), nullable=False),
        sa.Column("period_year", sa.Integer(), nullable=False),
        sa.Column("base_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("bonus_amount", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("deductions_amount", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("net_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("payment_method", expense_payment_method, nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["employee_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "employee_id", "period_year", "period_month", name="uq_salary_payments_employee_period"
        ),
    )
    op.create_index("ix_salary_payments_employee_id", "salary_payments", ["employee_id"])

    op.create_table(
        "salary_advances",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("employee_id", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("settled_in_payment_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["employee_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["settled_in_payment_id"], ["salary_payments.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_salary_advances_employee_id", "salary_advances", ["employee_id"])
    op.create_index("ix_salary_advances_date", "salary_advances", ["date"])
    op.create_index("ix_salary_advances_settled_in_payment_id", "salary_advances", ["settled_in_payment_id"])


def downgrade() -> None:
    op.drop_index("ix_salary_advances_settled_in_payment_id", table_name="salary_advances")
    op.drop_index("ix_salary_advances_date", table_name="salary_advances")
    op.drop_index("ix_salary_advances_employee_id", table_name="salary_advances")
    op.drop_table("salary_advances")

    op.drop_index("ix_salary_payments_employee_id", table_name="salary_payments")
    op.drop_table("salary_payments")

    op.drop_index("ix_expenses_date", table_name="expenses")
    op.drop_index("ix_expenses_category", table_name="expenses")
    op.drop_table("expenses")

    expense_payment_method.drop(op.get_bind(), checkfirst=True)
