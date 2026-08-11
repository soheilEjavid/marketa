"""An invoice-level discount must reduce reported profit.

SaleItem.line_total already nets off per-item discounts, but the
whole-invoice discount lives on Sale. Revenue (SUM of Sale.total) subtracts
it; profit did not, so a shop that gave a 5% discount on the whole basket
was shown a profit it had not actually earned — and net_profit(), which
sums this same column, inherited the error.
"""

from app.core.store_time import business_day_now
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models.entities import Category, Product
from app.schemas.sale import SaleCreate, SaleItemCreate, SalePaymentLineInput
from app.services.reports import daily_sales_summary, net_profit
from app.services.sales import process_sale


def _make_product(database: Session) -> Product:
    category = Category(name="cat", description="d")
    database.add(category)
    database.flush()
    product = Product(
        barcode="1",
        name="کالا",
        category=category,
        purchase_price=Decimal("600"),   # cost
        sale_price=Decimal("1000"),      # price
        stock_quantity=Decimal("100"),
        low_stock_threshold=Decimal("1"),
        is_active=True,
    )
    database.add(product)
    database.commit()
    return product


def test_invoice_discount_reduces_reported_profit() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as database:
        product = _make_product(database)

        # 10 units at 1,000 = 10,000 of goods, costing 600 each = 6,000.
        # A 1,500 discount is then given on the whole invoice.
        process_sale(
            database,
            SaleCreate(
                invoice_number="S-DISC",
                discount=Decimal("1500"),
                items=[SaleItemCreate(product_id=product.id, quantity=Decimal("10"))],
                payment_lines=[SalePaymentLineInput(method="cash", amount=Decimal("8500"))],
            ),
        )

        # The store's trading day, which is what daily_sales_summary()
        # buckets on. Asking for the UTC day instead fails between 20:30
        # UTC and midnight, when Tehran has already turned over — by the
        # clock rather than by the code.
        today = business_day_now()
        rows = daily_sales_summary(database, from_date=today, to_date=today)
        assert len(rows) == 1, rows
        row = rows[0]

        # Revenue is what the customer actually paid:
        #   10,000 of goods - 1,500 discount = 8,500
        assert Decimal(str(row["total_sales"])) == Decimal("8500"), row["total_sales"]

        # Profit must be measured against that same revenue:
        #   8,500 revenue - 6,000 cost = 2,500
        # Before the fix this reported 4,000 — the full 10,000 of line totals
        # minus cost, as though the discount had never been given.
        assert Decimal(str(row["profit"])) == Decimal("2500"), row["profit"]

        # And the headline figure must agree: with no expenses recorded,
        # net profit is exactly the gross figure above.
        summary = net_profit(database, period_start=today, period_end=today)
        assert Decimal(str(summary["gross_profit"])) == Decimal("2500"), summary
        assert Decimal(str(summary["net_profit"])) == Decimal("2500"), summary


def test_profit_unaffected_when_no_invoice_discount() -> None:
    """The common case must be untouched by the fix."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as database:
        product = _make_product(database)
        process_sale(
            database,
            SaleCreate(
                invoice_number="S-PLAIN",
                items=[SaleItemCreate(product_id=product.id, quantity=Decimal("10"))],
                payment_lines=[SalePaymentLineInput(method="cash", amount=Decimal("10000"))],
            ),
        )

        # The store's trading day, which is what daily_sales_summary()
        # buckets on. Asking for the UTC day instead fails between 20:30
        # UTC and midnight, when Tehran has already turned over — by the
        # clock rather than by the code.
        today = business_day_now()
        row = daily_sales_summary(database, from_date=today, to_date=today)[0]
        assert Decimal(str(row["total_sales"])) == Decimal("10000"), row["total_sales"]
        assert Decimal(str(row["profit"])) == Decimal("4000"), row["profit"]
