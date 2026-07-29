"""Add Phase 3 party financial posting and explicit payments.

Revision ID: 20260717_02
Revises: 20260717_01
Create Date: 2026-07-17
"""
from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op

revision: str = "20260717_02"
down_revision: str | None = "20260717_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
payment_method = sa.Enum("CASH", "CARD", "CREDIT", "MIXED", name="paymentmethod")
payment_status = sa.Enum("PAID", "PARTIAL", "UNPAID", name="paymentstatus")


def timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    ]


def upgrade() -> None:
    with op.batch_alter_table("suppliers") as batch_op:
        batch_op.add_column(sa.Column("credit_limit", sa.Numeric(14, 2), nullable=False, server_default="0"))
    for table_name in ("sales", "purchases"):
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.add_column(sa.Column("remaining_amount", sa.Numeric(14, 2), nullable=False, server_default="0"))
            batch_op.add_column(sa.Column("payment_status", payment_status, nullable=False, server_default="UNPAID"))
        op.execute(sa.text(f"""UPDATE {table_name} SET remaining_amount = CASE WHEN total > paid_amount THEN total - paid_amount ELSE 0 END, payment_status = CASE WHEN paid_amount >= total THEN 'PAID' WHEN paid_amount > 0 THEN 'PARTIAL' ELSE 'UNPAID' END"""))
    op.create_table(
        "customer_payments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("sale_id", sa.Integer(), nullable=True),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("method", payment_method, nullable=False),
        sa.Column("reference", sa.String(length=120), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        *timestamps(),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"]),
        sa.ForeignKeyConstraint(["sale_id"], ["sales.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("customer_id", "sale_id", "paid_at"):
        op.create_index(f"ix_customer_payments_{column}", "customer_payments", [column])
    op.create_table(
        "supplier_payments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("supplier_id", sa.Integer(), nullable=False),
        sa.Column("purchase_id", sa.Integer(), nullable=True),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("method", payment_method, nullable=False),
        sa.Column("reference", sa.String(length=120), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        *timestamps(),
        sa.ForeignKeyConstraint(["purchase_id"], ["purchases.id"]),
        sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("supplier_id", "purchase_id", "paid_at"):
        op.create_index(f"ix_supplier_payments_{column}", "supplier_payments", [column])
    op.execute(sa.text("""UPDATE customers SET balance = COALESCE((SELECT SUM(remaining_amount) FROM sales WHERE sales.customer_id = customers.id AND sales.status = 'COMPLETED'), 0)"""))
    op.execute(sa.text("""UPDATE suppliers SET balance = COALESCE((SELECT SUM(remaining_amount) FROM purchases WHERE purchases.supplier_id = suppliers.id AND purchases.status = 'COMPLETED'), 0)"""))


def downgrade() -> None:
    op.drop_table("supplier_payments")
    op.drop_table("customer_payments")
    for table_name in ("purchases", "sales"):
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.drop_column("payment_status")
            batch_op.drop_column("remaining_amount")
    with op.batch_alter_table("suppliers") as batch_op:
        batch_op.drop_column("credit_limit")
    payment_status.drop(op.get_bind(), checkfirst=True)
