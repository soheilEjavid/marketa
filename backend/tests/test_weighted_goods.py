"""Selling by weight, checked against a calculation done by hand.

The quantity columns were always Numeric(14,3), so the risk here was never
that the database would refuse 2.350 — it was that something downstream
would quietly treat it as a count. These tests pin the whole chain for one
weighted sale: line total, stock, the inventory ledger row, margin, and the
loyalty points earned, each against a number worked out on paper rather
than read back off the code.
"""

from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.entities import (
    Customer,
    InventoryTransaction,
    InventoryTransactionType,
    Product,
)
from app.schemas.sale import SaleCreate, SaleItemCreate
from app.services.loyalty import POINTS_PER_TOMAN
from app.services.margin import calculate_margin_pct
from app.services.sales import process_sale

# ── The hand calculation ─────────────────────────────────────────────────
#
# Butter, sold by the kilo:
#   purchase_price =  40,000 per kg      sale_price = 50,000 per kg
#   stock          =      10.000 kg      sold       =      2.350 kg
#
#   line_total  = 50,000 x 2.350 = 117,500
#   cost        = 40,000 x 2.350 =  94,000
#   profit      = 117,500 - 94,000 = 23,500
#   margin %    = (50,000 - 40,000) / 50,000 x 100 = 20%   (per unit, so the
#                 weight does not enter into it)
#   stock after = 10.000 - 2.350 = 7.650 kg
#
# Loyalty, for a member paying the invoice in full:
#   margin multiplier = 20% / 10        = 2
#   dead-stock boost  = 2x              -> 4   (this product has never sold
#                                               before, so the boost applies)
#   eligible value    = 117,500 x 4     = 470,000
#   tier bonus        = 1x                      (no tier bonuses configured)
#   paid fraction     = 117,500/117,500 = 1
#   points            = 470,000 // 10,000 = 47, with 0 progress left over
COST_PER_KG = Decimal("40000")
PRICE_PER_KG = Decimal("50000")
OPENING_STOCK = Decimal("10.000")
WEIGHT_SOLD = Decimal("2.350")

EXPECTED_LINE_TOTAL = Decimal("117500.00")
EXPECTED_STOCK_AFTER = Decimal("7.650")
EXPECTED_MARGIN_PCT = Decimal("20")
EXPECTED_POINTS = 47


def _butter(database: Session) -> Product:
    product = Product(
        name="کره محلی",
        is_weighted=True,
        unit="کیلوگرم",
        purchase_price=COST_PER_KG,
        sale_price=PRICE_PER_KG,
        stock_quantity=OPENING_STOCK,
        low_stock_threshold=Decimal("1"),
        is_active=True,
    )
    database.add(product)
    database.commit()
    database.refresh(product)
    return product


def test_selling_2350_grams_matches_the_hand_calculation(db_session: Session) -> None:
    product = _butter(db_session)
    customer = Customer(full_name="مشتری وزنی", is_active=True, loyalty_member=True)
    db_session.add(customer)
    db_session.commit()

    sale = process_sale(
        db_session,
        SaleCreate(
            customer_id=customer.id,
            items=[SaleItemCreate(product_id=product.id, quantity=WEIGHT_SOLD)],
        ),
    )

    # The weight survived as a weight, not as a count.
    assert sale.items[0].quantity == WEIGHT_SOLD
    assert sale.items[0].line_total == EXPECTED_LINE_TOTAL
    assert sale.subtotal == EXPECTED_LINE_TOTAL
    assert sale.total == EXPECTED_LINE_TOTAL

    db_session.refresh(product)
    assert product.stock_quantity == EXPECTED_STOCK_AFTER

    movement = db_session.query(InventoryTransaction).one()
    assert movement.quantity_change == -WEIGHT_SOLD
    assert movement.transaction_type == InventoryTransactionType.SALE

    margin = calculate_margin_pct(sale.items[0].unit_price, sale.items[0].cost_price)
    assert margin == EXPECTED_MARGIN_PCT

    db_session.refresh(customer)
    assert customer.loyalty_points_balance == EXPECTED_POINTS
    assert customer.loyalty_progress_toman == Decimal("0.00")


def test_a_weighted_line_cannot_be_rounded_away_by_stock_validation(
    db_session: Session,
) -> None:
    """0.250 kg out of 0.500 kg in stock must be allowed. Truncating either
    side to a whole number would make this either impossible or unlimited."""
    product = _butter(db_session)
    product.stock_quantity = Decimal("0.500")
    db_session.commit()

    process_sale(
        db_session,
        SaleCreate(items=[SaleItemCreate(product_id=product.id, quantity=Decimal("0.250"))]),
    )

    db_session.refresh(product)
    assert product.stock_quantity == Decimal("0.250")


def test_old_tier_estimate_falls_by_the_weight_sold_not_by_one(
    db_session: Session,
) -> None:
    """The dual-price old-stock estimate used to drop by exactly 1 per
    invoice line whatever the quantity, which for a weighted product could
    not be right at any quantity."""
    product = _butter(db_session)
    product.is_dual_priced = True
    product.old_purchase_price = Decimal("30000")
    product.old_sale_price = Decimal("42000")
    product.old_price_stock_estimate = Decimal("6.000")
    db_session.commit()

    process_sale(
        db_session,
        SaleCreate(
            items=[
                SaleItemCreate(
                    product_id=product.id, quantity=Decimal("2.350"), price_tier="old"
                )
            ]
        ),
    )

    db_session.refresh(product)
    assert product.old_price_stock_estimate == Decimal("3.650")


def test_counted_products_are_untouched(db_session: Session) -> None:
    """The flag defaults off and changes nothing for an ordinary product."""
    tea = Product(
        name="چای",
        purchase_price=Decimal("50"),
        sale_price=Decimal("90"),
        stock_quantity=Decimal("10"),
        low_stock_threshold=Decimal("1"),
        is_active=True,
    )
    db_session.add(tea)
    db_session.commit()

    assert tea.is_weighted is False

    sale = process_sale(
        db_session,
        SaleCreate(items=[SaleItemCreate(product_id=tea.id, quantity=Decimal("3"))]),
    )
    assert sale.items[0].line_total == Decimal("270.00")
    db_session.refresh(tea)
    assert tea.stock_quantity == Decimal("7.000")
