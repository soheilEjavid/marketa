from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.base import Base
from app.models.entities import Product, Sale, SaleItem, Customer, User
from app.schemas.sale import SaleCreate, SaleItemCreate, SalePaymentLineInput
from app.services.reports import (
    daily_sales_summary,
    top_products,
    low_stock,
    inventory_summary,
    customer_balances,
    payment_method_breakdown,
    cashier_performance,
)
from app.services.sales import process_sale
from app.services.shifts import open_shift


def test_daily_sales_summary_returns_data() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as database:
        product = Product(
            name="Tea",
            purchase_price=Decimal("5"),
            sale_price=Decimal("10"),
            stock_quantity=Decimal("100"),
            low_stock_threshold=Decimal("2"),
            is_active=True,
        )
        database.add(product)
        database.commit()
        database.refresh(product)

        process_sale(
            database,
            SaleCreate(
                items=[SaleItemCreate(product_id=product.id, quantity=Decimal("2"))]
            ),
        )

        summary = daily_sales_summary(database)
        assert len(summary) > 0
        assert summary[0]["total_sales"] > 0
        assert summary[0]["transaction_count"] > 0
        assert summary[0]["profit"] > 0


def test_top_products_returns_ranked_products() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as database:
        tea = Product(name="Tea", purchase_price=Decimal("5"), sale_price=Decimal("10"), stock_quantity=Decimal("100"), low_stock_threshold=Decimal("2"), is_active=True)
        coffee = Product(name="Coffee", purchase_price=Decimal("7"), sale_price=Decimal("14"), stock_quantity=Decimal("100"), low_stock_threshold=Decimal("2"), is_active=True)
        database.add_all([tea, coffee])
        database.commit()
        database.refresh(tea)
        database.refresh(coffee)

        process_sale(database, SaleCreate(items=[SaleItemCreate(product_id=tea.id, quantity=Decimal("5"))]))
        process_sale(database, SaleCreate(items=[SaleItemCreate(product_id=coffee.id, quantity=Decimal("2"))]))

        top = top_products(database)
        assert len(top) >= 2
        assert top[0]["product_name"] == "Tea"
        assert "total_profit" in top[0]
        assert top[0]["total_profit"] > 0


def test_low_stock_detects_below_threshold() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as database:
        p1 = Product(name="Low", purchase_price=Decimal("5"), sale_price=Decimal("10"), stock_quantity=Decimal("1"), low_stock_threshold=Decimal("5"), is_active=True)
        p2 = Product(name="Ok", purchase_price=Decimal("5"), sale_price=Decimal("10"), stock_quantity=Decimal("10"), low_stock_threshold=Decimal("5"), is_active=True)
        database.add_all([p1, p2])
        database.commit()

        result = low_stock(database)
        assert len(result) == 1
        assert result[0]["product_name"] == "Low"


def test_inventory_summary_returns_all_active() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as database:
        p1 = Product(name="A", purchase_price=Decimal("10"), sale_price=Decimal("15"), stock_quantity=Decimal("5"), low_stock_threshold=Decimal("2"), is_active=True)
        p2 = Product(name="B", purchase_price=Decimal("20"), sale_price=Decimal("30"), stock_quantity=Decimal("3"), low_stock_threshold=Decimal("2"), is_active=False)
        database.add_all([p1, p2])
        database.commit()

        result = inventory_summary(database)
        assert len(result) == 1
        assert result[0]["estimated_value"] == Decimal("50.000")
        assert result[0]["total_stock_value"] == Decimal("50.000")
        assert result[0]["potential_profit"] == Decimal("25.000")


def test_customer_balances_returns_only_positive() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as database:
        c1 = Customer(full_name="Ali", balance=Decimal("100"))
        c2 = Customer(full_name="Bob", balance=Decimal("0"), is_active=True)
        c3 = Customer(full_name="Charlie", balance=Decimal("50"), is_active=False)
        database.add_all([c1, c2, c3])
        database.commit()

        result = customer_balances(database)
        assert len(result) == 1
        assert result[0]["customer_name"] == "Ali"


def test_payment_method_breakdown_splits_mixed_sale_by_actual_tender() -> None:
    """A 100,000 sale paid 60,000 cash / 40,000 card must show up as +60,000
    cash and +40,000 card — never as +100,000 under a "mixed" bucket."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as database:
        product = Product(
            name="Item", purchase_price=Decimal("5"), sale_price=Decimal("100000"),
            stock_quantity=Decimal("10"), low_stock_threshold=Decimal("1"), is_active=True,
        )
        database.add(product)
        database.commit()
        database.refresh(product)

        process_sale(
            database,
            SaleCreate(
                items=[SaleItemCreate(product_id=product.id, quantity=Decimal("1"))],
                payment_lines=[
                    SalePaymentLineInput(method="cash", amount=Decimal("60000")),
                    SalePaymentLineInput(method="card", amount=Decimal("40000")),
                ],
            ),
        )

        breakdown = {row["payment_method"]: row["total"] for row in payment_method_breakdown(database)}
        assert "mixed" not in breakdown
        assert breakdown["cash"] == Decimal("60000.00")
        assert breakdown["card"] == Decimal("40000.00")


def test_payment_method_breakdown_legacy_single_method_sale_unaffected() -> None:
    """A plain single-tender sale (no split) must report the same total under
    its own method as it did before this fix — via the lineless fallback."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as database:
        product = Product(
            name="Item", purchase_price=Decimal("5"), sale_price=Decimal("10"),
            stock_quantity=Decimal("10"), low_stock_threshold=Decimal("1"), is_active=True,
        )
        database.add(product)
        database.commit()
        database.refresh(product)

        # No customer, no payment_lines -> legacy path, no SalePaymentLine row
        # for a credit sale, full total bucketed under Sale.payment_method.
        process_sale(
            database,
            SaleCreate(
                items=[SaleItemCreate(product_id=product.id, quantity=Decimal("2"))],
                payment_method="credit",
                paid_amount=Decimal("0"),
            ),
        )

        breakdown = {row["payment_method"]: row["total"] for row in payment_method_breakdown(database)}
        assert breakdown["credit"] == Decimal("20.00")


def test_cashier_performance_breakdown_splits_mixed_sale_by_actual_tender() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as database:
        cashier = User(
            username="cashier1", password_hash="x", full_name="Test Cashier",
            role="cashier", is_active=True,
        )
        database.add(cashier)
        database.commit()
        database.refresh(cashier)

        open_shift(database, cashier_id=cashier.id, opening_cash=Decimal("0"))

        product = Product(
            name="Item", purchase_price=Decimal("5"), sale_price=Decimal("100000"),
            stock_quantity=Decimal("10"), low_stock_threshold=Decimal("1"), is_active=True,
        )
        database.add(product)
        database.commit()
        database.refresh(product)

        process_sale(
            database,
            SaleCreate(
                items=[SaleItemCreate(product_id=product.id, quantity=Decimal("1"))],
                payment_lines=[
                    SalePaymentLineInput(method="cash", amount=Decimal("60000")),
                    SalePaymentLineInput(method="card", amount=Decimal("40000")),
                ],
            ),
        )

        result = cashier_performance(database)
        assert len(result) == 1
        row_breakdown = result[0]["payment_method_breakdown"]
        assert "mixed" not in row_breakdown
        assert row_breakdown["cash"] == Decimal("60000.00")
        assert row_breakdown["card"] == Decimal("40000.00")
