"""How much of the reported profit is actually the shopkeeper's.

An invoice records what the goods cost when they were bought. If they cost
more to replace, part of the profit on it is not profit — it is the
difference the shop must find to put the same goods back on the shelf. Draw
it out as earnings and the stock shrinks every cycle while every report
stays green.
"""

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.store_time import business_day_now
from app.models.base import Base
from app.models.entities import Product, Purchase, Sale
from app.schemas.purchase import PurchaseCreate, PurchaseItemCreate
from app.schemas.sale import SaleCreate, SaleItemCreate, SalePaymentLineInput
from app.services.products import create_product
from app.schemas.product import ProductCreate
from app.services.purchases import process_purchase
from app.services.reports import replacement_cost_of_sales
from app.services.sales import process_sale


def _session() -> Session:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return Session(engine)


def _backdate(database: Session, model, days: int) -> None:
    """Put every row of `model` that many days in the past."""
    from datetime import UTC, datetime
    when = datetime.now(UTC) - timedelta(days=days)
    for row in database.scalars(__import__("sqlalchemy").select(model)):
        row.created_at = when
    database.commit()


def test_the_rice_example_by_hand() -> None:
    """Bought at 100,000, sold at 120,000, now costs 110,000. The report
    shows 20,000 of profit; only 10,000 of it can be taken out."""
    with _session() as database:
        product = create_product(database, ProductCreate(
            name="برنج", purchase_price=Decimal("100000"), sale_price=Decimal("120000"),
            stock_quantity=Decimal("10"), low_stock_threshold=Decimal("0")))

        process_sale(database, SaleCreate(
            invoice_number="S-1",
            items=[SaleItemCreate(product_id=product.id, quantity=Decimal("1"))],
            payment_lines=[SalePaymentLineInput(method="cash", amount=Decimal("120000"))]))

        # Restocking at the higher price is what makes the old profit
        # partly illusory.
        process_purchase(database, PurchaseCreate(
            invoice_number="P-1", confirm_dual_pricing=True,
            items=[PurchaseItemCreate(product_id=product.id, quantity=Decimal("5"),
                                      unit_cost=Decimal("110000"))]))

        today = business_day_now()
        result = replacement_cost_of_sales(database, today, today)

        assert result["book_profit"] == Decimal("20000.00"), "120,000 sold − 100,000 cost"
        assert result["restock_share"] == Decimal("10000.00"), "110,000 to replace − 100,000 paid"
        assert result["withdrawable_profit"] == Decimal("10000.00")


def test_a_falling_cost_gives_more_than_the_books_show() -> None:
    """The arithmetic is symmetric: if replacement is cheaper, the shop is
    better off than its own report says."""
    with _session() as database:
        product = create_product(database, ProductCreate(
            name="برنج", purchase_price=Decimal("100000"), sale_price=Decimal("120000"),
            stock_quantity=Decimal("10"), low_stock_threshold=Decimal("0")))
        process_sale(database, SaleCreate(
            invoice_number="S-1",
            items=[SaleItemCreate(product_id=product.id, quantity=Decimal("1"))],
            payment_lines=[SalePaymentLineInput(method="cash", amount=Decimal("120000"))]))
        process_purchase(database, PurchaseCreate(
            invoice_number="P-1", confirm_dual_pricing=True,
            items=[PurchaseItemCreate(product_id=product.id, quantity=Decimal("5"),
                                      unit_cost=Decimal("90000"))]))

        today = business_day_now()
        result = replacement_cost_of_sales(database, today, today)
        assert result["restock_share"] == Decimal("-10000.00")
        assert result["withdrawable_profit"] == Decimal("30000.00")


def test_stable_costs_leave_the_whole_profit_available() -> None:
    with _session() as database:
        product = create_product(database, ProductCreate(
            name="برنج", purchase_price=Decimal("100000"), sale_price=Decimal("120000"),
            stock_quantity=Decimal("10"), low_stock_threshold=Decimal("0")))
        process_sale(database, SaleCreate(
            invoice_number="S-1",
            items=[SaleItemCreate(product_id=product.id, quantity=Decimal("2"))],
            payment_lines=[SalePaymentLineInput(method="cash", amount=Decimal("240000"))]))

        today = business_day_now()
        result = replacement_cost_of_sales(database, today, today)
        assert result["book_profit"] == Decimal("40000.00")
        assert result["restock_share"] == Decimal("0.00"), "nothing bought since; nothing to make up"
        assert result["withdrawable_profit"] == Decimal("40000.00")


def test_replacement_is_priced_at_the_period_end_not_today() -> None:
    """A month must not look worse simply for being further in the past.
    Sold in the reported month at the cost of the time; the price rose
    again *after* it, and that later rise is not that month's business."""
    with _session() as database:
        product = create_product(database, ProductCreate(
            name="برنج", purchase_price=Decimal("100000"), sale_price=Decimal("200000"),
            stock_quantity=Decimal("100"), low_stock_threshold=Decimal("0")))
        process_sale(database, SaleCreate(
            invoice_number="S-OLD",
            items=[SaleItemCreate(product_id=product.id, quantity=Decimal("1"))],
            payment_lines=[SalePaymentLineInput(method="cash", amount=Decimal("200000"))]))
        _backdate(database, Sale, days=60)

        # The newest cost known *by* the reported day: 110,000. Dated a day
        # before it, so it is on the right side of `<= period_end`.
        process_purchase(database, PurchaseCreate(
            invoice_number="P-THEN", confirm_dual_pricing=True,
            items=[PurchaseItemCreate(product_id=product.id, quantity=Decimal("1"),
                                      unit_cost=Decimal("110000"))]))
        _backdate(database, Purchase, days=61)

        # Long after it: 200,000. Irrelevant to that month.
        process_purchase(database, PurchaseCreate(
            invoice_number="P-NOW", confirm_dual_pricing=True,
            items=[PurchaseItemCreate(product_id=product.id, quantity=Decimal("1"),
                                      unit_cost=Decimal("200000"))]))

        month = business_day_now() - timedelta(days=60)
        result = replacement_cost_of_sales(database, month, month)
        assert result["restock_share"] == Decimal("10000.00"), (
            "priced against the 110,000 of the time, not the 200,000 of today"
        )


def test_a_line_with_no_purchase_history_is_counted_and_flagged() -> None:
    """Opening stock never bought through an invoice keeps its own cost.
    Dropping it would quietly understate the very figure this raises."""
    with _session() as database:
        product = create_product(database, ProductCreate(
            name="کالای دستی", purchase_price=Decimal("50000"), sale_price=Decimal("80000"),
            stock_quantity=Decimal("10"), low_stock_threshold=Decimal("0")))
        process_sale(database, SaleCreate(
            invoice_number="S-1",
            items=[SaleItemCreate(product_id=product.id, quantity=Decimal("2"))],
            payment_lines=[SalePaymentLineInput(method="cash", amount=Decimal("160000"))]))

        today = business_day_now()
        result = replacement_cost_of_sales(database, today, today)
        assert result["book_profit"] == Decimal("60000.00")
        assert result["restock_share"] == Decimal("0.00"), "its own cost is the best figure there is"
        assert result["products_counted"] == 1
        assert result["products_with_estimated_cost"] == 1, "and the report says so"
