"""A sale that fails must leave nothing at all behind.

process_sale() is documented as one transaction: the document, its line
items, the stock change and the inventory ledger rows either all land or
none of them do. That guarantee was broken by a commit() reached through
decrement_old_stock_estimate(), which runs from inside _build_sale_items()
between the stock decrement and the InventoryTransaction that explains it.
The result was the worst shape this data can take: stock silently missing
with no ledger row accounting for it, plus an orphan `completed` invoice
carrying a zero total.

The trigger was routine rather than exotic — any dual-priced product on the
old tier in a cart where a later check fails, and "later check" includes
the customer credit limit, which a shop rejects on an ordinary day.
"""

from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.models.entities import Customer, InventoryTransaction, Product, Sale, SaleItem
from app.schemas.sale import SaleCreate, SaleItemCreate
from app.services.sales import SaleError, process_sale


def _dual_priced(database: Session) -> Product:
    product = Product(
        name="Dual-priced rice",
        purchase_price=Decimal("100"),
        sale_price=Decimal("150"),
        stock_quantity=Decimal("10"),
        low_stock_threshold=Decimal("1"),
        is_active=True,
        is_dual_priced=True,
        old_purchase_price=Decimal("80"),
        old_sale_price=Decimal("120"),
        old_price_stock_estimate=4,
    )
    database.add(product)
    return product


def _plain(database: Session) -> Product:
    product = Product(
        name="Plain tea",
        purchase_price=Decimal("50"),
        sale_price=Decimal("90"),
        stock_quantity=Decimal("10"),
        low_stock_threshold=Decimal("1"),
        is_active=True,
    )
    database.add(product)
    return product


def _assert_nothing_persisted(database: Session, dual: Product, plain: Product) -> None:
    database.expire_all()
    assert database.query(Sale).count() == 0, "a failed sale left an invoice behind"
    assert database.query(SaleItem).count() == 0, "a failed sale left line items behind"
    assert database.query(InventoryTransaction).count() == 0
    assert database.get(Product, dual.id).stock_quantity == Decimal("10.000"), (
        "stock was decremented by a sale that failed"
    )
    assert database.get(Product, dual.id).old_price_stock_estimate == 4
    assert database.get(Product, plain.id).stock_quantity == Decimal("10.000")


def test_failed_line_validation_rolls_back_the_dual_priced_line(db_session: Session) -> None:
    """Line 1 is the dual-priced product that reaches the commit; line 2
    then fails validation, part-way through the same loop."""
    dual, plain = _dual_priced(db_session), _plain(db_session)
    db_session.commit()

    with pytest.raises(SaleError):
        process_sale(
            db_session,
            SaleCreate(
                items=[
                    SaleItemCreate(product_id=dual.id, quantity=Decimal("5"), price_tier="old"),
                    SaleItemCreate(
                        product_id=plain.id, quantity=Decimal("1"), discount=Decimal("99999")
                    ),
                ]
            ),
        )

    _assert_nothing_persisted(db_session, dual, plain)


def test_credit_limit_rejection_rolls_back_the_dual_priced_line(db_session: Session) -> None:
    """The realistic path: the whole cart is valid, and the sale is refused
    at the very end because the customer is over their credit limit."""
    dual, plain = _dual_priced(db_session), _plain(db_session)
    customer = Customer(
        full_name="Over-limit customer",
        credit_limit=Decimal("100"),
        balance=Decimal("0"),
        is_active=True,
    )
    db_session.add(customer)
    db_session.commit()

    with pytest.raises(SaleError):
        process_sale(
            db_session,
            SaleCreate(
                customer_id=customer.id,
                # 5 x 120 = 600, far past the 100 limit, and nothing is tendered
                items=[SaleItemCreate(product_id=dual.id, quantity=Decimal("5"), price_tier="old")],
                paid_amount=Decimal("0"),
            ),
        )

    _assert_nothing_persisted(db_session, dual, plain)
    db_session.expire_all()
    assert db_session.get(Customer, customer.id).balance == Decimal("0.00")
