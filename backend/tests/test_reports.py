from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.base import Base
from app.models.entities import Product, Sale, SaleItem, Customer
from app.schemas.sale import SaleCreate, SaleItemCreate
from app.services.reports import (
    daily_sales_summary,
    top_products,
    low_stock,
    inventory_summary,
    customer_balances,
)
from app.services.sales import process_sale


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
