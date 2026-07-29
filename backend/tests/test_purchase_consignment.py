from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.base import Base
from app.models.entities import PaymentStatus, Product, Supplier
from app.schemas.purchase import PurchaseCreate, PurchaseEditRequest, PurchaseItemCreate
from app.services.purchases import (
    ConsignmentError,
    edit_purchase,
    get_purchase,
    list_outstanding_consignment,
    process_purchase,
    settle_consignment_item,
)


def _make_product(database: Session, name: str = "Tea", stock: str = "0") -> Product:
    product = Product(
        name=name,
        purchase_price=Decimal("5"),
        sale_price=Decimal("10"),
        stock_quantity=Decimal(stock),
        low_stock_threshold=Decimal("2"),
        is_active=True,
    )
    database.add(product)
    database.commit()
    database.refresh(product)
    return product


def _make_supplier(database: Session) -> Supplier:
    supplier = Supplier(name="Dairy Co", is_active=True)
    database.add(supplier)
    database.commit()
    database.refresh(supplier)
    return supplier


def test_consignment_item_increases_stock_but_not_purchase_total() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as database:
        supplier = _make_supplier(database)
        normal_product = _make_product(database, name="Sugar")
        consignment_product = _make_product(database, name="Yogurt")

        purchase = process_purchase(
            database,
            PurchaseCreate(
                supplier_id=supplier.id,
                items=[
                    PurchaseItemCreate(product_id=normal_product.id, quantity=Decimal("10"), unit_cost=Decimal("5")),
                    PurchaseItemCreate(
                        product_id=consignment_product.id,
                        quantity=Decimal("20"),
                        unit_cost=Decimal("3"),
                        is_consignment=True,
                    ),
                ],
            ),
        )

        # Stock increases for BOTH items regardless of consignment flag.
        database.refresh(normal_product)
        database.refresh(consignment_product)
        assert normal_product.stock_quantity == Decimal("10.000")
        assert consignment_product.stock_quantity == Decimal("20.000")

        # Only the normal item's value (10*5=50) counts toward the payable total.
        assert purchase.total == Decimal("50")
        assert purchase.remaining_amount == Decimal("50")
        assert purchase.payment_status == PaymentStatus.UNPAID

        database.refresh(supplier)
        assert supplier.balance == Decimal("50")

        consignment_item = next(item for item in purchase.items if item.is_consignment)
        assert consignment_item.consignment_settled_at is None
        assert consignment_item.line_total == Decimal("60")


def test_settle_consignment_item_adds_to_payable_total() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as database:
        supplier = _make_supplier(database)
        consignment_product = _make_product(database, name="Yogurt")

        purchase = process_purchase(
            database,
            PurchaseCreate(
                supplier_id=supplier.id,
                items=[
                    PurchaseItemCreate(
                        product_id=consignment_product.id,
                        quantity=Decimal("20"),
                        unit_cost=Decimal("3"),
                        is_consignment=True,
                    ),
                ],
            ),
        )
        assert purchase.total == Decimal("0")

        consignment_item = purchase.items[0]
        settled = settle_consignment_item(database, consignment_item)

        assert settled.consignment_settled_at is not None

        purchase = get_purchase(database, purchase.id)
        assert purchase.total == Decimal("60")
        assert purchase.remaining_amount == Decimal("60")
        assert purchase.payment_status == PaymentStatus.UNPAID

        database.refresh(supplier)
        assert supplier.balance == Decimal("60")

        # Now excluded from the outstanding-consignment listing.
        assert list_outstanding_consignment(database) == []


def test_settle_already_settled_item_raises() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as database:
        product = _make_product(database)
        purchase = process_purchase(
            database,
            PurchaseCreate(
                items=[
                    PurchaseItemCreate(
                        product_id=product.id, quantity=Decimal("5"), unit_cost=Decimal("2"), is_consignment=True
                    ),
                ],
            ),
        )
        item = purchase.items[0]
        settle_consignment_item(database, item)

        with pytest.raises(ConsignmentError):
            settle_consignment_item(database, item)


def test_settle_non_consignment_item_raises() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as database:
        product = _make_product(database)
        purchase = process_purchase(
            database,
            PurchaseCreate(
                items=[PurchaseItemCreate(product_id=product.id, quantity=Decimal("5"), unit_cost=Decimal("2"))],
            ),
        )
        item = purchase.items[0]

        with pytest.raises(ConsignmentError):
            settle_consignment_item(database, item)


def test_edit_purchase_preserves_consignment_flag_and_excludes_it_from_total() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as database:
        normal_product = _make_product(database, name="Sugar")
        consignment_product = _make_product(database, name="Yogurt")

        purchase = process_purchase(
            database,
            PurchaseCreate(
                items=[
                    PurchaseItemCreate(product_id=normal_product.id, quantity=Decimal("10"), unit_cost=Decimal("5")),
                    PurchaseItemCreate(
                        product_id=consignment_product.id,
                        quantity=Decimal("20"),
                        unit_cost=Decimal("3"),
                        is_consignment=True,
                    ),
                ],
            ),
        )
        assert purchase.total == Decimal("50")

        normal_item = next(item for item in purchase.items if not item.is_consignment)
        consignment_item = next(item for item in purchase.items if item.is_consignment)

        # Bump both quantities via an edit — including sending
        # is_consignment=True back for the consignment line, which the
        # edit path must ignore (it's already True from creation, but this
        # also proves an edit can't be used to flip an existing line's flag).
        updated, _ = edit_purchase(
            database,
            purchase,
            PurchaseEditRequest(
                items=[
                    PurchaseItemCreate(
                        id=normal_item.id, product_id=normal_product.id, quantity=Decimal("12"), unit_cost=Decimal("5")
                    ),
                    PurchaseItemCreate(
                        id=consignment_item.id,
                        product_id=consignment_product.id,
                        quantity=Decimal("25"),
                        unit_cost=Decimal("3"),
                        is_consignment=False,
                    ),
                ],
            ),
        )

        # Total only reflects the normal line (12*5=60); the consignment
        # line's new value (25*3=75) is still excluded despite growing.
        assert updated.total == Decimal("60")

        updated_consignment_item = next(item for item in updated.items if item.id == consignment_item.id)
        assert updated_consignment_item.is_consignment is True
        assert updated_consignment_item.quantity == Decimal("25.000")

        database.refresh(consignment_product)
        assert consignment_product.stock_quantity == Decimal("25.000")
