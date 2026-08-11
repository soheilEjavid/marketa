"""Opening stock is a stock movement like any other.

A new product may be entered with units already on the shelf. That quantity
used to go straight into `Product.stock_quantity` with nothing in the
inventory ledger, on the reasoning that a new product has no history — but
the units exist, and `stock == Σ movements` is what the whole financial
audit rests on.

The cost of that noise is worse than the noise. Once unexplained
differences are normal, a real one gets waved through as "just another
opening balance", and the audit stops being an audit.
"""

from decimal import Decimal

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.models.base import Base
from app.models.entities import InventoryTransaction, InventoryTransactionType, Product
from app.schemas.product import ProductCreate
from app.schemas.purchase import PurchaseCreate, PurchaseItemCreate
from app.schemas.sale import SaleCreate, SaleItemCreate
from app.services.products import create_product
from app.services.purchases import process_purchase
from app.services.sales import process_sale


def _session() -> Session:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return Session(engine)


def _ledger(database: Session, product_id: int) -> Decimal:
    return Decimal(str(database.scalar(
        select(func.coalesce(func.sum(InventoryTransaction.quantity_change), 0))
        .where(InventoryTransaction.product_id == product_id)) or 0))


def test_opening_stock_is_logged_as_a_movement() -> None:
    with _session() as database:
        product = create_product(database, ProductCreate(
            name="ذغال", purchase_price=Decimal("100000"), sale_price=Decimal("150000"),
            stock_quantity=Decimal("2"), low_stock_threshold=Decimal("0")))

        assert product.stock_quantity == Decimal("2.000")
        assert _ledger(database, product.id) == Decimal("2.000"), "the shelf and the ledger agree"

        movement = database.scalars(
            select(InventoryTransaction).where(InventoryTransaction.product_id == product.id)).one()
        assert movement.transaction_type == InventoryTransactionType.ADJUSTMENT
        assert movement.quantity_change == Decimal("2.000")


def test_the_invariant_survives_the_sale_that_used_to_expose_it() -> None:
    """The real case: a product typed in with two on the shelf, then 1.2
    sold. Stock read 0.800 and the ledger read −1.200 — right answer, no
    way to explain it."""
    with _session() as database:
        product = create_product(database, ProductCreate(
            name="ذغال", purchase_price=Decimal("100000"), sale_price=Decimal("150000"),
            stock_quantity=Decimal("2"), low_stock_threshold=Decimal("0")))
        process_sale(database, SaleCreate(
            invoice_number="S-1",
            items=[SaleItemCreate(product_id=product.id, quantity=Decimal("1.2"))]))

        database.refresh(product)
        assert product.stock_quantity == Decimal("0.800")
        assert _ledger(database, product.id) == Decimal("0.800")


def test_a_product_with_no_opening_stock_logs_nothing() -> None:
    with _session() as database:
        product = create_product(database, ProductCreate(
            name="کالای جدید", purchase_price=Decimal("100"), sale_price=Decimal("150"),
            stock_quantity=Decimal("0"), low_stock_threshold=Decimal("0")))
        assert database.scalars(
            select(InventoryTransaction).where(InventoryTransaction.product_id == product.id)
        ).all() == [], "an empty shelf is not a movement"


def test_opening_stock_without_a_cost_is_refused() -> None:
    """purchase_price defaults to zero. Stock entered against that zero
    becomes its cost basis, and the next delivery averages against it —
    understating the cost of the line for good."""
    with pytest.raises(ValueError, match="needs a purchase price"):
        ProductCreate(name="بی‌قیمت", sale_price=Decimal("150"),
                      stock_quantity=Decimal("5"), low_stock_threshold=Decimal("0"))


def test_opening_stock_carries_its_cost_into_the_next_delivery() -> None:
    """The point of insisting on a price: the weighted average has
    something honest to blend against."""
    with _session() as database:
        product = create_product(database, ProductCreate(
            name="برنج", purchase_price=Decimal("50000"), sale_price=Decimal("80000"),
            stock_quantity=Decimal("10"), low_stock_threshold=Decimal("0")))

        process_purchase(database, PurchaseCreate(
            invoice_number="P-1", confirm_dual_pricing=True,
            items=[PurchaseItemCreate(product_id=product.id, quantity=Decimal("20"),
                                      unit_cost=Decimal("65000"))]))
        database.refresh(product)

        # (10×50,000 + 20×65,000) / 30 = 60,000 — the same answer as if the
        # opening ten had arrived on a purchase invoice.
        assert product.purchase_price == Decimal("60000.00")
        assert product.stock_quantity == Decimal("30.000")
        assert _ledger(database, product.id) == Decimal("30.000")
