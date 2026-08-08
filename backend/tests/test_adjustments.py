from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models.base import Base
from app.models.entities import (
    InventoryTransaction,
    InventoryTransactionType,
    Product,
    Sale,
    Purchase,
)
from app.schemas.sale import SaleCreate, SaleItemCreate
from app.schemas.purchase import PurchaseCreate, PurchaseItemCreate
from app.services.adjustments import (
    AdjustmentError,
    ProductNotFoundError,
    adjust_stock,
    return_sale_items,
    return_purchase_items,
)
from app.services.sales import process_sale
from app.services.purchases import process_purchase


def create_product(
    database: Session, *, name: str, stock: str, sale_price: str = "10"
) -> Product:
    product = Product(
        name=name,
        purchase_price=Decimal("5"),
        sale_price=Decimal(sale_price),
        stock_quantity=Decimal(stock),
        low_stock_threshold=Decimal("2"),
        is_active=True,
    )
    database.add(product)
    database.commit()
    database.refresh(product)
    return product


def test_adjust_stock_increases_quantity_and_creates_transaction() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as database:
        product = create_product(database, name="Sugar", stock="10")
        result = adjust_stock(database, product.id, Decimal("5"))
        database.refresh(product)

        assert result.stock_quantity == Decimal("15.000")
        assert product.stock_quantity == Decimal("15.000")
        tx = database.scalar(select(InventoryTransaction).order_by(InventoryTransaction.id.desc()))
        assert tx is not None
        assert tx.quantity_change == Decimal("5.000")
        assert tx.transaction_type == InventoryTransactionType.ADJUSTMENT


def test_adjust_stock_decreases_quantity() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as database:
        product = create_product(database, name="Sugar", stock="10")
        adjust_stock(database, product.id, Decimal("-3"))
        database.refresh(product)
        assert product.stock_quantity == Decimal("7.000")


def test_adjust_stock_raises_on_negative_stock() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as database:
        product = create_product(database, name="Sugar", stock="2")
        with pytest.raises(AdjustmentError, match="Insufficient stock"):
            adjust_stock(database, product.id, Decimal("-5"))


def test_adjust_stock_raises_on_missing_product() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as database:
        with pytest.raises(ProductNotFoundError):
            adjust_stock(database, 999, Decimal("5"))


def test_return_sale_items_restores_stock() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as database:
        tea = create_product(database, name="Tea", stock="10")
        sale = process_sale(
            database,
            SaleCreate(
                items=[SaleItemCreate(product_id=tea.id, quantity=Decimal("3"))]
            ),
        )
        database.refresh(tea)
        assert tea.stock_quantity == Decimal("7.000")

        return_sale_items(database, sale.id, [{"product_id": tea.id, "quantity": Decimal("2")}])
        database.refresh(tea)
        assert tea.stock_quantity == Decimal("9.000")


def test_return_purchase_items_decreases_stock() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as database:
        rice = create_product(database, name="Rice", stock="5")
        purchase = process_purchase(
            database,
            PurchaseCreate(
                # Restocking at a cost the product has not carried before, with
                # stock still on the shelf, trips the dual-pricing gate — see
                # services/purchases.py. Confirming without
                # dual_pricing_new_sale_prices keeps one price.
                confirm_dual_pricing=True,
                items=[PurchaseItemCreate(product_id=rice.id, quantity=Decimal("10"), unit_cost=Decimal("8"))]
            ),
        )
        database.refresh(rice)
        assert rice.stock_quantity == Decimal("15.000")

        return_purchase_items(database, purchase.id, [{"product_id": rice.id, "quantity": Decimal("3")}])
        database.refresh(rice)
        assert rice.stock_quantity == Decimal("12.000")


def test_return_purchase_items_raises_on_negative_stock() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as database:
        rice = create_product(database, name="Rice", stock="2")
        purchase = process_purchase(
            database,
            PurchaseCreate(
                confirm_dual_pricing=True,  # see the note in the test above
                items=[PurchaseItemCreate(product_id=rice.id, quantity=Decimal("1"), unit_cost=Decimal("8"))]
            ),
        )
        with pytest.raises(AdjustmentError, match="Insufficient stock"):
            return_purchase_items(database, purchase.id, [{"product_id": rice.id, "quantity": Decimal("10")}])