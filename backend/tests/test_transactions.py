from decimal import Decimal

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.models.base import Base
from app.models.entities import (
    InventoryTransaction,
    InventoryTransactionType,
    Product,
    Purchase,
    Sale,
)
from app.schemas.purchase import PurchaseCreate, PurchaseEditRequest, PurchaseItemCreate
from app.schemas.sale import SaleCreate, SaleEditRequest, SaleItemCreate
from app.services.purchases import edit_purchase, process_purchase
from app.services.sales import InsufficientStockError, edit_sale, hold_sale, process_sale


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


def test_sale_updates_stock_and_creates_inventory_transactions() -> None:
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
        transaction = database.scalar(select(InventoryTransaction))

        assert sale.status.value == "completed"
        assert sale.total == Decimal("30.00")
        assert tea.stock_quantity == Decimal("7.000")
        assert transaction is not None
        assert transaction.quantity_change == Decimal("-3.000")
        assert transaction.transaction_type == InventoryTransactionType.SALE
        assert transaction.related_id == sale.id


def test_sale_rolls_back_everything_when_stock_is_insufficient() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as database:
        tea = create_product(database, name="Tea", stock="10")
        coffee = create_product(database, name="Coffee", stock="1")

        with pytest.raises(InsufficientStockError):
            process_sale(
                database,
                SaleCreate(
                    items=[
                        SaleItemCreate(
                            product_id=tea.id, quantity=Decimal("2")
                        ),
                        SaleItemCreate(
                            product_id=coffee.id, quantity=Decimal("2")
                        ),
                    ]
                ),
            )

        database.refresh(tea)
        database.refresh(coffee)
        sale_count = database.scalar(select(func.count()).select_from(Sale))
        transaction_count = database.scalar(
            select(func.count()).select_from(InventoryTransaction)
        )

        assert tea.stock_quantity == Decimal("10.000")
        assert coffee.stock_quantity == Decimal("1.000")
        assert sale_count == 0
        assert transaction_count == 0


def test_purchase_updates_stock_cost_and_inventory() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as database:
        tea = create_product(database, name="Tea", stock="4")
        purchase = process_purchase(
            database,
            PurchaseCreate(
                items=[
                    PurchaseItemCreate(
                        product_id=tea.id,
                        quantity=Decimal("6"),
                        unit_cost=Decimal("6.25"),
                    )
                ]
            ),
        )
        database.refresh(tea)
        transaction = database.scalar(select(InventoryTransaction))
        purchase_count = database.scalar(select(func.count()).select_from(Purchase))

        assert purchase.total == Decimal("37.50")
        assert tea.stock_quantity == Decimal("10.000")
        assert tea.purchase_price == Decimal("6.25")
        assert transaction is not None
        assert transaction.quantity_change == Decimal("6.000")
        assert transaction.transaction_type == InventoryTransactionType.PURCHASE
        assert transaction.related_id == purchase.id
        assert purchase_count == 1


def test_purchase_item_optional_fields_are_nullable_and_do_not_block_entry() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as database:
        tea = create_product(database, name="Tea", stock="4")
        purchase = process_purchase(
            database,
            PurchaseCreate(
                items=[
                    PurchaseItemCreate(
                        product_id=tea.id,
                        quantity=Decimal("2"),
                        unit_cost=Decimal("6.25"),
                    )
                ]
            ),
        )

        saved_item = purchase.items[0]
        database.refresh(tea)

        assert saved_item.selling_price is None
        assert saved_item.expiry_date is None
        assert purchase.total == Decimal("12.50")
        assert tea.stock_quantity == Decimal("6.000")


def test_process_sale_merges_duplicate_product_lines_into_one() -> None:
    """Scanning/selecting the same product twice in one invoice must become
    one merged line (summed quantity), not two SaleItem rows."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as database:
        tea = create_product(database, name="Tea", stock="100")
        sale = process_sale(
            database,
            SaleCreate(
                items=[
                    SaleItemCreate(product_id=tea.id, quantity=Decimal("2")),
                    SaleItemCreate(product_id=tea.id, quantity=Decimal("3")),
                ]
            ),
        )
        assert len(sale.items) == 1
        assert sale.items[0].quantity == Decimal("5.000")
        database.refresh(tea)
        assert tea.stock_quantity == Decimal("95.000")


def test_process_sale_merge_keeps_first_occurrence_price_on_conflict() -> None:
    """A raw request with conflicting unit_price for the same product_id
    across two lines must deterministically keep the FIRST occurrence's
    price (the UI never produces this; only a direct API call could)."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as database:
        tea = create_product(database, name="Tea", stock="100")
        sale = process_sale(
            database,
            SaleCreate(
                items=[
                    SaleItemCreate(product_id=tea.id, quantity=Decimal("2"), unit_price=Decimal("11")),
                    SaleItemCreate(product_id=tea.id, quantity=Decimal("3"), unit_price=Decimal("99")),
                ]
            ),
        )
        assert len(sale.items) == 1
        assert sale.items[0].quantity == Decimal("5.000")
        assert sale.items[0].unit_price == Decimal("11.00")


def test_hold_sale_merges_duplicate_product_lines() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as database:
        tea = create_product(database, name="Tea", stock="100")
        held = hold_sale(
            database,
            SaleCreate(
                items=[
                    SaleItemCreate(product_id=tea.id, quantity=Decimal("1")),
                    SaleItemCreate(product_id=tea.id, quantity=Decimal("4")),
                ]
            ),
        )
        assert len(held.items) == 1
        assert held.items[0].quantity == Decimal("5.000")


def test_edit_sale_merges_duplicate_product_lines() -> None:
    """Adding a product already on the invoice, via an edit, must merge into
    the existing line rather than create a second one."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as database:
        tea = create_product(database, name="Tea", stock="100")
        sale = process_sale(
            database,
            SaleCreate(items=[SaleItemCreate(product_id=tea.id, quantity=Decimal("2"))]),
        )
        existing_item = sale.items[0]

        updated, _ = edit_sale(
            database,
            sale,
            SaleEditRequest(
                items=[
                    SaleItemCreate(id=existing_item.id, product_id=tea.id, quantity=Decimal("2")),
                    # A brand-new line for the SAME product, id=None.
                    SaleItemCreate(product_id=tea.id, quantity=Decimal("3")),
                ]
            ),
        )
        assert len(updated.items) == 1
        assert updated.items[0].quantity == Decimal("5.000")
        database.refresh(tea)
        assert tea.stock_quantity == Decimal("95.000")


def test_process_purchase_merges_duplicate_product_lines_into_one() -> None:
    # stock="0" so the (unrelated, pre-existing) dual-pricing-confirmation
    # gate never triggers -- these tests only care about the merge.
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as database:
        tea = create_product(database, name="Tea", stock="0")
        purchase = process_purchase(
            database,
            PurchaseCreate(
                items=[
                    PurchaseItemCreate(product_id=tea.id, quantity=Decimal("2"), unit_cost=Decimal("6.25")),
                    PurchaseItemCreate(product_id=tea.id, quantity=Decimal("3"), unit_cost=Decimal("6.25")),
                ]
            ),
        )
        assert len(purchase.items) == 1
        assert purchase.items[0].quantity == Decimal("5.000")
        database.refresh(tea)
        assert tea.stock_quantity == Decimal("5.000")


def test_process_purchase_merge_keeps_first_occurrence_cost_on_conflict() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as database:
        tea = create_product(database, name="Tea", stock="0")
        purchase = process_purchase(
            database,
            PurchaseCreate(
                items=[
                    PurchaseItemCreate(product_id=tea.id, quantity=Decimal("2"), unit_cost=Decimal("6.25")),
                    PurchaseItemCreate(product_id=tea.id, quantity=Decimal("3"), unit_cost=Decimal("50")),
                ]
            ),
        )
        assert len(purchase.items) == 1
        assert purchase.items[0].quantity == Decimal("5.000")
        assert purchase.items[0].unit_cost == Decimal("6.25")


def test_edit_purchase_merges_duplicate_product_lines() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as database:
        tea = create_product(database, name="Tea", stock="0")
        purchase = process_purchase(
            database,
            PurchaseCreate(
                items=[PurchaseItemCreate(product_id=tea.id, quantity=Decimal("2"), unit_cost=Decimal("6.25"))]
            ),
        )
        existing_item = purchase.items[0]

        updated, _ = edit_purchase(
            database,
            purchase,
            PurchaseEditRequest(
                items=[
                    PurchaseItemCreate(
                        id=existing_item.id, product_id=tea.id, quantity=Decimal("2"), unit_cost=Decimal("6.25")
                    ),
                    # A brand-new line for the SAME product, id=None.
                    PurchaseItemCreate(product_id=tea.id, quantity=Decimal("3"), unit_cost=Decimal("6.25")),
                ]
            ),
        )
        assert len(updated.items) == 1
        assert updated.items[0].quantity == Decimal("5.000")
        database.refresh(tea)
        assert tea.stock_quantity == Decimal("5.000")
