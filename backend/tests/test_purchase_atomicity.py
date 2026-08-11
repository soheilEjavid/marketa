"""A delivery that is refused must leave nothing behind.

process_purchase() commits once at the end, so a failure is meant to take
the whole document with it. enable_dual_pricing() broke that: it committed
on its own, and _apply_dual_pricing() calls it from inside that transaction
*before* the Purchase row even exists.

The result was a product left dual-priced by a delivery that never
happened — carrying prices from goods that never arrived, with no purchase
recorded and an audit row for an event that did not occur. The till then
offers the cashier a tier choice for a batch that is not on the shelf.

This is the third instance of one pattern in this codebase: a helper
committing partway through somebody else's transaction.
"""

from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models.base import Base
from app.models.entities import AuditLog, InventoryTransaction, Product, Purchase
from app.schemas.purchase import PurchaseCreate, PurchaseItemCreate, PurchasePaymentLineInput
from app.services.purchases import PurchaseError, process_purchase


def _session() -> Session:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return Session(engine)


def _product(database: Session) -> Product:
    product = Product(
        name="پنیر", purchase_price=Decimal("50000"), sale_price=Decimal("70000"),
        stock_quantity=Decimal("10"), low_stock_threshold=Decimal("0"), is_active=True,
    )
    database.add(product)
    database.commit()
    database.refresh(product)
    return product


def test_a_refused_delivery_does_not_leave_the_product_dual_priced() -> None:
    with _session() as database:
        product = _product(database)

        with pytest.raises(PurchaseError, match="cannot exceed"):
            process_purchase(database, PurchaseCreate(
                invoice_number="P-FAIL",
                confirm_dual_pricing=True,
                dual_pricing_new_sale_prices={product.id: 90000},
                items=[PurchaseItemCreate(product_id=product.id, quantity=Decimal("5"),
                                          unit_cost=Decimal("65000"))],
                # Overpaid on purpose: this trips the guard *after*
                # _apply_dual_pricing() has already run.
                payment_lines=[PurchasePaymentLineInput(method="cash", amount=Decimal("999999999"))],
            ))

        database.expire_all()
        product = database.get(Product, product.id)
        assert product.is_dual_priced is False, "no delivery, no price split"
        assert product.sale_price == Decimal("70000.00"), "the shelf price is untouched"
        assert product.purchase_price == Decimal("50000.00")
        assert product.old_sale_price is None
        assert product.dual_price_started_at is None
        assert product.stock_quantity == Decimal("10.000")

        assert database.scalars(select(Purchase)).all() == []
        assert database.scalars(select(InventoryTransaction)).all() == []
        assert database.scalars(select(AuditLog)).all() == [], (
            "and no audit row for a delivery that never happened"
        )


def test_a_successful_dual_priced_delivery_still_lands_whole() -> None:
    """The guard must not have cost the feature: when the purchase succeeds,
    the price split and the document commit together."""
    with _session() as database:
        product = _product(database)

        purchase = process_purchase(database, PurchaseCreate(
            invoice_number="P-OK",
            confirm_dual_pricing=True,
            dual_pricing_new_sale_prices={product.id: 90000},
            items=[PurchaseItemCreate(product_id=product.id, quantity=Decimal("5"),
                                      unit_cost=Decimal("65000"))],
            payment_lines=[PurchasePaymentLineInput(method="cash", amount=Decimal("325000"))],
        ))

        database.expire_all()
        product = database.get(Product, product.id)
        assert purchase.total == Decimal("325000.00")
        assert product.is_dual_priced is True
        assert product.sale_price == Decimal("90000.00"), "the new batch's price"
        assert product.old_sale_price == Decimal("70000.00"), "the old batch keeps its own"
        assert product.purchase_price == Decimal("65000.00")
        assert product.stock_quantity == Decimal("15.000")
        assert len(database.scalars(select(AuditLog)).all()) == 1, "one audit row, committed with the rest"
