from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models.base import Base
from app.models.entities import (
    Customer,
    DocumentStatus,
    LoyaltyPointTransaction,
    LoyaltyTransactionType,
    PaymentMethod,
    Product,
    Sale,
    SaleItem,
    SalePaymentLine,
    User,
)
from app.schemas.customer import CustomerCreate
from app.schemas.financial import PaymentCreate
from app.schemas.sale import SaleCreate, SaleItemCreate, SalePaymentLineInput
from app.services.customers import create_customer
from app.services.financials import record_customer_payment
from app.services.loyalty import (
    CHURN_RECOVERY_REASON,
    TIER_BRONZE,
    TIER_GOLD,
    TIER_SILVER,
    LoyaltyError,
    adjust_points_manually,
    award_points_for_payment,
    customer_tier,
    get_loyalty_settings,
    issue_churn_recovery_coupons,
    max_redeemable_points,
    redeem_points,
    reward_catalog,
    reward_suggestions,
    sweep_expired_points,
    update_loyalty_settings,
)
from app.services.reports import customer_tiers_report, loyalty_redemptions
from app.services.sales import process_sale


def _make_customer(database: Session) -> Customer:
    customer = Customer(full_name="Test Customer", credit_limit=Decimal("1000000"))
    database.add(customer)
    database.commit()
    database.refresh(customer)
    return customer


def _make_product(database: Session, *, purchase_price: str, sale_price: str, name: str = "Item") -> Product:
    product = Product(
        name=name,
        purchase_price=Decimal(purchase_price),
        sale_price=Decimal(sale_price),
        stock_quantity=Decimal("1000"),
        low_stock_threshold=Decimal("2"),
        is_active=True,
    )
    database.add(product)
    database.commit()
    database.refresh(product)
    return product


def _seed_sale_history(database: Session, product: Product, *, days_ago: int) -> None:
    """Give `product` a completed-sale history `days_ago` days in the past,
    so _is_dead_stock() sees it as recently sold (days_ago < lookback) or
    still dead (days_ago > lookback) as needed — isolating margin-rate
    tests from the dead-stock boost, and setting up dead-stock tests
    explicitly.
    """
    sale = Sale(
        invoice_number=f"SEED-{product.id}-{uuid4().hex[:8]}",
        status=DocumentStatus.COMPLETED,
        payment_method=PaymentMethod.CASH,
        created_at=datetime.now(UTC) - timedelta(days=days_ago),
    )
    database.add(sale)
    database.flush()
    database.add(
        SaleItem(
            sale_id=sale.id,
            product_id=product.id,
            quantity=Decimal("1"),
            unit_price=Decimal("1"),
            cost_price=Decimal("1"),
            discount=Decimal("0"),
            line_total=Decimal("1"),
        )
    )
    database.commit()


# ── Margin-proportional scoring (10% margin -> 1x rate, 30% -> 3x rate) ──

def test_margin_proportional_10_percent_earns_base_rate() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as database:
        customer = _make_customer(database)
        # 10% margin: 900 cost / 1000 sale -> multiplier = 10/10 = 1x.
        product = _make_product(database, purchase_price="900", sale_price="1000")
        _seed_sale_history(database, product, days_ago=5)  # not dead stock

        process_sale(
            database,
            SaleCreate(
                customer_id=customer.id,
                payment_method="cash",
                items=[SaleItemCreate(product_id=product.id, quantity=Decimal("100"))],
            ),
        )
        database.refresh(customer)
        # line_total = 100,000; eligible = 100,000 * 1 = 100,000 -> 10 points.
        assert customer.loyalty_points_balance == 10


def test_margin_proportional_30_percent_earns_triple_rate() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as database:
        customer = _make_customer(database)
        # 30% margin: 700 cost / 1000 sale -> multiplier = 30/10 = 3x.
        product = _make_product(database, purchase_price="700", sale_price="1000")
        _seed_sale_history(database, product, days_ago=5)  # not dead stock

        process_sale(
            database,
            SaleCreate(
                customer_id=customer.id,
                payment_method="cash",
                items=[SaleItemCreate(product_id=product.id, quantity=Decimal("100"))],
            ),
        )
        database.refresh(customer)
        # line_total = 100,000; eligible = 100,000 * 3 = 300,000 -> 30 points.
        assert customer.loyalty_points_balance == 30


def test_negative_margin_item_earns_no_points() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as database:
        customer = _make_customer(database)
        # -10% margin: 1100 cost / 1000 sale (below-cost / clearance item).
        product = _make_product(database, purchase_price="1100", sale_price="1000")
        _seed_sale_history(database, product, days_ago=5)

        process_sale(
            database,
            SaleCreate(
                customer_id=customer.id,
                payment_method="cash",
                items=[SaleItemCreate(product_id=product.id, quantity=Decimal("20"))],
            ),
        )
        database.refresh(customer)
        assert customer.loyalty_points_balance == 0


def test_mixed_margin_sale_weights_each_line_independently() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as database:
        customer = _make_customer(database)
        healthy = _make_product(database, purchase_price="700", sale_price="1000", name="Healthy")
        negative = _make_product(database, purchase_price="1100", sale_price="1000", name="Negative")
        _seed_sale_history(database, healthy, days_ago=5)
        _seed_sale_history(database, negative, days_ago=5)

        process_sale(
            database,
            SaleCreate(
                customer_id=customer.id,
                payment_method="cash",
                items=[
                    SaleItemCreate(product_id=healthy.id, quantity=Decimal("15")),  # 15,000 @ 3x
                    SaleItemCreate(product_id=negative.id, quantity=Decimal("15")),  # 15,000 @ 0x
                ],
            ),
        )
        database.refresh(customer)
        # eligible = 15,000*3 + 15,000*0 = 45,000 -> 4 points.
        assert customer.loyalty_points_balance == 4


def test_credit_sale_earns_no_points_until_actually_paid() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as database:
        customer = _make_customer(database)
        product = _make_product(database, purchase_price="700", sale_price="1000")
        _seed_sale_history(database, product, days_ago=5)

        sale = process_sale(
            database,
            SaleCreate(
                customer_id=customer.id,
                payment_method="credit",
                paid_amount=Decimal("0"),
                items=[SaleItemCreate(product_id=product.id, quantity=Decimal("20"))],
            ),
        )
        database.refresh(customer)
        assert customer.loyalty_points_balance == 0

        # Now the customer pays off the balance later — points earn at that point.
        payment = record_customer_payment(
            database, customer, PaymentCreate(amount=Decimal("20000"), document_id=sale.id, method=PaymentMethod.CASH)
        )
        award_points_for_payment(database, customer, sale, payment.amount)
        database.commit()
        database.refresh(customer)
        # eligible = 20,000 * 3 = 60,000 -> 6 points.
        assert customer.loyalty_points_balance == 6


# ── Dead-stock earn boost ─────────────────────────────────────────────

def test_never_sold_product_counts_as_dead_stock_on_its_first_sale() -> None:
    """Matches services/reports.py::dead_stock()'s existing convention:
    a product with no sale history at all is treated as dead stock
    regardless of age — so its very first sale already earns the boost.
    This also exercises the no-threshold-configured membership default:
    the customer becomes a member immediately.
    """
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as database:
        customer = _make_customer(database)
        # 30% margin -> 3x; never sold -> dead-stock 2x boost -> 6x total.
        product = _make_product(database, purchase_price="700", sale_price="1000")

        process_sale(
            database,
            SaleCreate(
                customer_id=customer.id,
                payment_method="cash",
                items=[SaleItemCreate(product_id=product.id, quantity=Decimal("20"))],
            ),
        )
        database.refresh(customer)
        # line_total = 20,000; eligible = 20,000 * 3 * 2 = 120,000 -> 12 points.
        assert customer.loyalty_points_balance == 12
        assert customer.loyalty_member is True


def test_dead_stock_product_earns_boosted_points() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as database:
        customer = _make_customer(database)
        product = _make_product(database, purchase_price="700", sale_price="1000")  # 30% margin -> 3x
        _seed_sale_history(database, product, days_ago=45)  # older than the 30-day lookback

        process_sale(
            database,
            SaleCreate(
                customer_id=customer.id,
                payment_method="cash",
                items=[SaleItemCreate(product_id=product.id, quantity=Decimal("10"))],
            ),
        )
        database.refresh(customer)
        # line_total = 10,000; eligible = 10,000 * 3 * 2 (dead-stock boost) = 60,000 -> 6 points.
        assert customer.loyalty_points_balance == 6


def test_recently_sold_product_does_not_get_dead_stock_boost() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as database:
        customer = _make_customer(database)
        product = _make_product(database, purchase_price="700", sale_price="1000")  # 30% margin -> 3x
        _seed_sale_history(database, product, days_ago=5)  # within the 30-day lookback

        process_sale(
            database,
            SaleCreate(
                customer_id=customer.id,
                payment_method="cash",
                items=[SaleItemCreate(product_id=product.id, quantity=Decimal("10"))],
            ),
        )
        database.refresh(customer)
        # line_total = 10,000; eligible = 10,000 * 3 (no boost) = 30,000 -> 3 points.
        assert customer.loyalty_points_balance == 3


# ── Manager-configurable auto-enrollment threshold ────────────────────

def test_membership_gated_by_invoice_total_threshold() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as database:
        update_loyalty_settings(
            database, min_invoice_total=Decimal("50000"), min_invoice_profit=None, user_id=None
        )
        customer = _make_customer(database)
        product = _make_product(database, purchase_price="700", sale_price="1000")  # 30% margin

        # First sale is below the threshold -> no membership, no points.
        process_sale(
            database,
            SaleCreate(
                customer_id=customer.id,
                payment_method="cash",
                items=[SaleItemCreate(product_id=product.id, quantity=Decimal("10"))],  # total = 10,000
            ),
        )
        database.refresh(customer)
        assert customer.loyalty_member is False
        assert customer.loyalty_points_balance == 0

        # Second sale crosses the threshold -> membership granted, and this
        # qualifying invoice itself already earns points (no dead-stock
        # boost this time: the product now has recent sale history from
        # the first sale above).
        process_sale(
            database,
            SaleCreate(
                customer_id=customer.id,
                payment_method="cash",
                items=[SaleItemCreate(product_id=product.id, quantity=Decimal("60"))],  # total = 60,000
            ),
        )
        database.refresh(customer)
        assert customer.loyalty_member is True
        # eligible = 60,000 * 3 = 180,000 -> 18 points.
        assert customer.loyalty_points_balance == 18


# ── Post-checkout membership-earned flag (transient, on SaleRead only) ──

def test_sale_flags_membership_just_earned_only_on_the_crossing_sale() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as database:
        update_loyalty_settings(
            database, min_invoice_total=Decimal("50000"), min_invoice_profit=None, user_id=None
        )
        customer = _make_customer(database)
        product = _make_product(database, purchase_price="700", sale_price="1000")

        below_threshold = process_sale(
            database,
            SaleCreate(
                customer_id=customer.id,
                payment_method="cash",
                items=[SaleItemCreate(product_id=product.id, quantity=Decimal("10"))],  # 10,000
            ),
        )
        assert below_threshold.loyalty_membership_just_earned is False

        crossing_sale = process_sale(
            database,
            SaleCreate(
                customer_id=customer.id,
                payment_method="cash",
                items=[SaleItemCreate(product_id=product.id, quantity=Decimal("60"))],  # 60,000
            ),
        )
        assert crossing_sale.loyalty_membership_just_earned is True

        # Customer is already a member now — a further sale must not flag
        # again (it didn't just cross anything).
        already_member_sale = process_sale(
            database,
            SaleCreate(
                customer_id=customer.id,
                payment_method="cash",
                items=[SaleItemCreate(product_id=product.id, quantity=Decimal("60"))],
            ),
        )
        assert already_member_sale.loyalty_membership_just_earned is False


def test_sale_without_customer_never_flags_membership_just_earned() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as database:
        update_loyalty_settings(
            database, min_invoice_total=Decimal("50000"), min_invoice_profit=None, user_id=None
        )
        product = _make_product(database, purchase_price="700", sale_price="1000")

        sale = process_sale(
            database,
            SaleCreate(
                payment_method="cash",
                items=[SaleItemCreate(product_id=product.id, quantity=Decimal("60"))],  # 60,000, no customer
            ),
        )
        assert sale.loyalty_membership_just_earned is False


# ── Quick-add customer created as an immediate loyalty member ───────────

def test_customer_can_be_created_as_loyalty_member_immediately() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as database:
        customer = create_customer(
            database, CustomerCreate(full_name="Quick-add Customer", loyalty_member=True)
        )
        assert customer.loyalty_member is True

        default_customer = create_customer(database, CustomerCreate(full_name="Regular Customer"))
        assert default_customer.loyalty_member is False


def test_membership_gated_by_invoice_profit_threshold() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as database:
        update_loyalty_settings(
            database, min_invoice_total=None, min_invoice_profit=Decimal("20000"), user_id=None
        )
        customer = _make_customer(database)
        # 30% margin: profit per unit = 300 toman.
        product = _make_product(database, purchase_price="700", sale_price="1000")
        _seed_sale_history(database, product, days_ago=5)  # isolate from dead-stock boost

        # qty=100 -> profit = 300*100 = 30,000 >= 20,000 threshold.
        process_sale(
            database,
            SaleCreate(
                customer_id=customer.id,
                payment_method="cash",
                items=[SaleItemCreate(product_id=product.id, quantity=Decimal("100"))],
            ),
        )
        database.refresh(customer)
        assert customer.loyalty_member is True
        # eligible = 100,000 * 3 = 300,000 -> 30 points.
        assert customer.loyalty_points_balance == 30


def test_update_loyalty_settings_roundtrip() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as database:
        defaults = get_loyalty_settings(database)
        assert defaults.min_invoice_total_for_membership is None
        assert defaults.min_invoice_profit_for_membership is None

        update_loyalty_settings(
            database,
            min_invoice_total=Decimal("50000"),
            min_invoice_profit=Decimal("10000"),
            user_id=1,
        )

        reloaded = get_loyalty_settings(database)
        assert reloaded.min_invoice_total_for_membership == Decimal("50000.00")
        assert reloaded.min_invoice_profit_for_membership == Decimal("10000.00")
        assert reloaded.updated_by_user_id == 1


# ── Redemption, expiry, manual adjustment (unaffected by scoring changes) ──

def test_redemption_reduces_sale_balance_and_point_balance() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as database:
        customer = _make_customer(database)
        adjust_points_manually(database, customer, 10, reason="seed for test", user_id=None)
        product = _make_product(database, purchase_price="700", sale_price="1000")

        # A 100,000 toman sale, paid partly with points.
        sale = process_sale(
            database,
            SaleCreate(
                customer_id=customer.id,
                payment_method="credit",
                paid_amount=Decimal("0"),
                items=[SaleItemCreate(product_id=product.id, quantity=Decimal("100"))],
                redeem_points=6,  # 6 * 500 = 3,000 toman, well under the 30% cap of 30,000
            ),
        )
        database.refresh(customer)
        assert customer.loyalty_points_balance == 4  # 10 - 6
        assert sale.paid_amount == Decimal("3000.00")
        assert sale.remaining_amount == Decimal("97000.00")


def test_redemption_over_cap_is_rejected() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as database:
        customer = _make_customer(database)
        adjust_points_manually(database, customer, 100, reason="seed for test", user_id=None)
        product = _make_product(database, purchase_price="700", sale_price="1000")

        with pytest.raises(Exception, match="cannot exceed"):
            process_sale(
                database,
                SaleCreate(
                    customer_id=customer.id,
                    payment_method="credit",
                    paid_amount=Decimal("0"),
                    items=[SaleItemCreate(product_id=product.id, quantity=Decimal("10"))],  # 10,000 total
                    redeem_points=100,  # 100 * 500 = 50,000 toman -- way over 30% of 10,000
                ),
            )


def test_redemption_combined_with_cash_and_card_payment_lines() -> None:
    """Points redemption + a split cash/card payment on the same sale: the
    redeem-first ordering must hold (payment lines are checked against the
    post-redemption remainder), and award_points_for_payment() must be safe
    to call once per line without re-triggering the autoflush bug that was
    previously fixed (sale.items must still be visible via the flush that
    already happens before any of this)."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as database:
        customer = _make_customer(database)
        adjust_points_manually(database, customer, 10, reason="seed for test", user_id=None)
        product = _make_product(database, purchase_price="700", sale_price="1000")

        # total = 100,000. redeem 6 points = 3,000 toman (well under the 30%
        # cap of 30,000) -> remaining = 97,000, split 50,000 cash / 47,000 card.
        sale = process_sale(
            database,
            SaleCreate(
                customer_id=customer.id,
                items=[SaleItemCreate(product_id=product.id, quantity=Decimal("100"))],
                redeem_points=6,
                payment_lines=[
                    SalePaymentLineInput(method="cash", amount=Decimal("50000")),
                    SalePaymentLineInput(method="card", amount=Decimal("47000")),
                ],
            ),
        )

        assert sale.total == Decimal("100000.00")
        assert sale.paid_amount == Decimal("100000.00")
        assert sale.remaining_amount == Decimal("0.00")
        assert sale.payment_method == "mixed"

        lines = database.scalars(
            select(SalePaymentLine).where(SalePaymentLine.sale_id == sale.id).order_by(SalePaymentLine.id)
        ).all()
        assert [(line.method, line.amount) for line in lines] == [
            ("cash", Decimal("50000.00")),
            ("card", Decimal("47000.00")),
        ]

        database.refresh(customer)
        # margin 30% -> 3x multiplier, first-ever sale of this product -> 2x
        # dead-stock boost -> 6x. eligible_value = 100,000 * 6 = 600,000.
        # Earned across the two payment-line calls (50% then 47% of total)
        # sums identically to a single 97% call: 58 points, matching the
        # existing single-call earn-rate tests' math style.
        assert customer.loyalty_points_balance == 10 - 6 + 58


def test_max_redeemable_points_respects_both_cap_and_balance() -> None:
    # 30% of 100,000 = 30,000 toman = 60 points at 500/point.
    assert max_redeemable_points(Decimal("100000"), available_points=1000) == 60
    # Balance is the binding constraint here.
    assert max_redeemable_points(Decimal("100000"), available_points=10) == 10


def test_expired_points_are_swept_and_deducted() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as database:
        customer = _make_customer(database)
        customer.loyalty_points_balance = 5
        database.add(
            LoyaltyPointTransaction(
                customer_id=customer.id,
                points=5,
                transaction_type=LoyaltyTransactionType.EARN,
                expires_at=datetime.now(UTC) - timedelta(days=1),
            )
        )
        database.commit()

        expired = sweep_expired_points(database, customer)
        database.commit()
        assert expired == 5
        assert customer.loyalty_points_balance == 0

        expire_rows = database.scalars(
            select(LoyaltyPointTransaction).where(
                LoyaltyPointTransaction.customer_id == customer.id,
                LoyaltyPointTransaction.transaction_type == LoyaltyTransactionType.EXPIRE,
            )
        ).all()
        assert len(expire_rows) == 1
        assert expire_rows[0].points == -5


def test_manual_adjustment_requires_reason_and_logs_transaction() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as database:
        customer = _make_customer(database)

        with pytest.raises(LoyaltyError, match="reason"):
            adjust_points_manually(database, customer, 10, reason="", user_id=1)

        updated = adjust_points_manually(database, customer, 10, reason="Goodwill gesture", user_id=1)
        assert updated.loyalty_points_balance == 10

        with pytest.raises(LoyaltyError, match="negative"):
            adjust_points_manually(database, customer, -20, reason="Oops", user_id=1)


def test_untied_payment_without_a_sale_earns_no_points() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as database:
        customer = _make_customer(database)
        customer.balance = Decimal("5000")
        database.commit()

        payment = record_customer_payment(
            database, customer, PaymentCreate(amount=Decimal("5000"), method=PaymentMethod.CASH)
        )
        award_points_for_payment(database, customer, None, payment.amount)
        database.commit()
        database.refresh(customer)
        assert customer.loyalty_points_balance == 0


# ── Per-product loyalty point override ────────────────────────────────

def test_product_override_replaces_automatic_calculation() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as database:
        customer = _make_customer(database)
        # 30% margin (would normally be 3x) and never sold before (would
        # normally also get the 2x dead-stock boost -> 6x automatic total).
        product = _make_product(database, purchase_price="700", sale_price="1000")
        product.loyalty_point_multiplier = Decimal("1")  # manager override: flat 1x
        database.commit()

        process_sale(
            database,
            SaleCreate(
                customer_id=customer.id,
                payment_method="cash",
                items=[SaleItemCreate(product_id=product.id, quantity=Decimal("20"))],
            ),
        )
        database.refresh(customer)
        # line_total = 20,000; override multiplier = 1 -> eligible = 20,000 -> 2 points
        # (not 12, which is what the automatic margin+dead-stock calc would give).
        assert customer.loyalty_points_balance == 2


def test_product_override_zero_exempts_product_despite_healthy_margin() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as database:
        customer = _make_customer(database)
        product = _make_product(database, purchase_price="700", sale_price="1000")
        product.loyalty_point_multiplier = Decimal("0")
        database.commit()

        process_sale(
            database,
            SaleCreate(
                customer_id=customer.id,
                payment_method="cash",
                items=[SaleItemCreate(product_id=product.id, quantity=Decimal("20"))],
            ),
        )
        database.refresh(customer)
        assert customer.loyalty_points_balance == 0


# ── Reward suggestions (dead-stock + near-expiry) ─────────────────────

def test_reward_suggestions_prioritizes_near_expiry_and_flags_affordability() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as database:
        customer = _make_customer(database)
        adjust_points_manually(database, customer, 12, reason="seed for test", user_id=None)

        near_expiry = _make_product(database, purchase_price="1", sale_price="5000", name="NearExpiry")
        near_expiry.expiration_date = datetime.now(UTC).date() + timedelta(days=5)
        near_expiry.stock_quantity = Decimal("10")
        database.commit()

        dead_stock = _make_product(database, purchase_price="1", sale_price="10000", name="DeadStock")
        dead_stock.stock_quantity = Decimal("10")
        database.commit()
        _seed_sale_history(database, dead_stock, days_ago=45)

        neither = _make_product(database, purchase_price="1", sale_price="3000", name="Neither")
        neither.stock_quantity = Decimal("10")
        database.commit()
        _seed_sale_history(database, neither, days_ago=5)

        rows = reward_suggestions(database, customer)
        product_ids = [row["product_id"] for row in rows]
        assert near_expiry.id in product_ids
        assert dead_stock.id in product_ids
        assert neither.id not in product_ids
        # near-expiry sorted first
        assert rows[0]["product_id"] == near_expiry.id
        assert rows[0]["reason"] == "near_expiry"
        assert rows[0]["points_required"] == 10  # 5000 / 500
        assert rows[0]["affordable"] is True
        dead_stock_row = next(row for row in rows if row["product_id"] == dead_stock.id)
        assert dead_stock_row["reason"] == "dead_stock"
        assert dead_stock_row["points_required"] == 20  # 10000 / 500
        assert dead_stock_row["affordable"] is False  # only 12 points available


# ── Customer tiers (bronze/silver/gold) ───────────────────────────────

def test_customer_tier_is_bronze_when_tiers_not_configured() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as database:
        customer = _make_customer(database)
        product = _make_product(database, purchase_price="1", sale_price="1000000")
        process_sale(
            database,
            SaleCreate(
                customer_id=customer.id,
                payment_method="cash",
                items=[SaleItemCreate(product_id=product.id, quantity=Decimal("1"))],
            ),
        )
        assert customer_tier(database, customer) == TIER_BRONZE


def test_customer_tier_promotes_at_silver_and_gold_thresholds() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as database:
        update_loyalty_settings(
            database,
            min_invoice_total=None,
            min_invoice_profit=None,
            user_id=None,
            tier_silver_min_spend=Decimal("50000"),
            tier_gold_min_spend=Decimal("200000"),
        )
        customer = _make_customer(database)
        product = _make_product(database, purchase_price="1", sale_price="1000")

        process_sale(
            database,
            SaleCreate(
                customer_id=customer.id,
                payment_method="cash",
                items=[SaleItemCreate(product_id=product.id, quantity=Decimal("20"))],  # 20,000
            ),
        )
        assert customer_tier(database, customer) == TIER_BRONZE

        process_sale(
            database,
            SaleCreate(
                customer_id=customer.id,
                payment_method="cash",
                items=[SaleItemCreate(product_id=product.id, quantity=Decimal("40"))],  # +40,000 = 60,000
            ),
        )
        assert customer_tier(database, customer) == TIER_SILVER

        process_sale(
            database,
            SaleCreate(
                customer_id=customer.id,
                payment_method="cash",
                items=[SaleItemCreate(product_id=product.id, quantity=Decimal("150"))],  # +150,000 = 210,000
            ),
        )
        assert customer_tier(database, customer) == TIER_GOLD


def test_customer_tiers_report_disabled_and_sorted() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as database:
        assert customer_tiers_report(database) == []

        update_loyalty_settings(
            database,
            min_invoice_total=None,
            min_invoice_profit=None,
            user_id=None,
            tier_silver_min_spend=Decimal("50000"),
            tier_gold_min_spend=Decimal("200000"),
        )
        gold_customer = _make_customer(database)
        bronze_customer = _make_customer(database)
        product = _make_product(database, purchase_price="1", sale_price="1000")

        process_sale(
            database,
            SaleCreate(
                customer_id=gold_customer.id,
                payment_method="cash",
                items=[SaleItemCreate(product_id=product.id, quantity=Decimal("250"))],  # 250,000
            ),
        )
        process_sale(
            database,
            SaleCreate(
                customer_id=bronze_customer.id,
                payment_method="cash",
                items=[SaleItemCreate(product_id=product.id, quantity=Decimal("10"))],  # 10,000
            ),
        )

        rows = customer_tiers_report(database)
        assert rows[0]["customer_id"] == gold_customer.id
        assert rows[0]["tier"] == TIER_GOLD
        assert rows[-1]["customer_id"] == bronze_customer.id
        assert rows[-1]["tier"] == TIER_BRONZE


# ── Automated churn-recovery coupon issuance ──────────────────────────

def _seed_customer_sale(database: Session, customer: Customer, product: Product, *, days_ago: int) -> None:
    sale = Sale(
        invoice_number=f"CHURN-{customer.id}-{uuid4().hex[:8]}",
        customer_id=customer.id,
        status=DocumentStatus.COMPLETED,
        payment_method=PaymentMethod.CASH,
        created_at=datetime.now(UTC) - timedelta(days=days_ago),
    )
    database.add(sale)
    database.flush()
    database.add(
        SaleItem(
            sale_id=sale.id,
            product_id=product.id,
            quantity=Decimal("1"),
            unit_price=Decimal("1000"),
            cost_price=Decimal("700"),
            discount=Decimal("0"),
            line_total=Decimal("1000"),
        )
    )
    database.commit()


def test_issue_churn_recovery_coupons_noop_when_not_configured() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as database:
        assert issue_churn_recovery_coupons(database, user_id=None) == []


def test_issue_churn_recovery_coupons_grants_once_per_cooldown() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as database:
        update_loyalty_settings(
            database, min_invoice_total=None, min_invoice_profit=None, user_id=None,
            churn_recovery_coupon_points=15,
        )
        customer = _make_customer(database)
        customer.loyalty_member = True
        database.commit()
        product = _make_product(database, purchase_price="700", sale_price="1000")
        _seed_customer_sale(database, customer, product, days_ago=40)
        _seed_customer_sale(database, customer, product, days_ago=60)

        issued = issue_churn_recovery_coupons(database, user_id=1)
        assert len(issued) == 1
        assert issued[0]["customer_id"] == customer.id
        assert issued[0]["points"] == 15
        database.refresh(customer)
        assert customer.loyalty_points_balance == 15

        rows = database.scalars(
            select(LoyaltyPointTransaction).where(
                LoyaltyPointTransaction.customer_id == customer.id,
                LoyaltyPointTransaction.reason == CHURN_RECOVERY_REASON,
            )
        ).all()
        assert len(rows) == 1

        # Re-running immediately should not double-issue within the cooldown.
        issued_again = issue_churn_recovery_coupons(database, user_id=1)
        assert issued_again == []
        database.refresh(customer)
        assert customer.loyalty_points_balance == 15


def test_issue_churn_recovery_coupons_skips_non_members() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as database:
        update_loyalty_settings(
            database, min_invoice_total=None, min_invoice_profit=None, user_id=None,
            churn_recovery_coupon_points=15,
        )
        customer = _make_customer(database)
        customer.loyalty_member = False
        database.commit()
        product = _make_product(database, purchase_price="700", sale_price="1000")
        _seed_customer_sale(database, customer, product, days_ago=40)
        _seed_customer_sale(database, customer, product, days_ago=60)

        assert issue_churn_recovery_coupons(database, user_id=None) == []


# ── Tier-linked earn-rate bonus ───────────────────────────────────────

def test_tier_earn_bonus_applied_for_gold_customer() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as database:
        update_loyalty_settings(
            database, min_invoice_total=None, min_invoice_profit=None, user_id=None,
            tier_gold_min_spend=Decimal("100000"), tier_gold_earn_bonus=Decimal("2"),
        )
        customer = _make_customer(database)
        product = _make_product(database, purchase_price="700", sale_price="1000")  # 30% margin -> 3x
        _seed_sale_history(database, product, days_ago=5)

        process_sale(
            database,
            SaleCreate(
                customer_id=customer.id,
                payment_method="cash",
                items=[SaleItemCreate(product_id=product.id, quantity=Decimal("100"))],  # total = 100,000
            ),
        )
        database.refresh(customer)
        assert customer_tier(database, customer) == TIER_GOLD
        # eligible = 100,000*3 = 300,000; gold bonus 2x -> 600,000 -> 60 points
        assert customer.loyalty_points_balance == 60


def test_tier_earn_bonus_applied_for_silver_customer() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as database:
        update_loyalty_settings(
            database, min_invoice_total=None, min_invoice_profit=None, user_id=None,
            tier_silver_min_spend=Decimal("50000"), tier_silver_earn_bonus=Decimal("1.5"),
        )
        customer = _make_customer(database)
        product = _make_product(database, purchase_price="700", sale_price="1000")  # 30% margin -> 3x
        _seed_sale_history(database, product, days_ago=5)

        process_sale(
            database,
            SaleCreate(
                customer_id=customer.id,
                payment_method="cash",
                items=[SaleItemCreate(product_id=product.id, quantity=Decimal("50"))],  # total = 50,000
            ),
        )
        database.refresh(customer)
        assert customer_tier(database, customer) == TIER_SILVER
        # eligible = 50,000*3 = 150,000; silver bonus 1.5x -> 225,000 -> 22 points
        assert customer.loyalty_points_balance == 22


def test_bronze_customer_gets_no_earn_bonus() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as database:
        update_loyalty_settings(
            database, min_invoice_total=None, min_invoice_profit=None, user_id=None,
            tier_silver_min_spend=Decimal("999999999"), tier_silver_earn_bonus=Decimal("5"),
        )
        customer = _make_customer(database)
        product = _make_product(database, purchase_price="700", sale_price="1000")
        _seed_sale_history(database, product, days_ago=5)

        process_sale(
            database,
            SaleCreate(
                customer_id=customer.id,
                payment_method="cash",
                items=[SaleItemCreate(product_id=product.id, quantity=Decimal("20"))],  # total = 20,000
            ),
        )
        database.refresh(customer)
        assert customer_tier(database, customer) == TIER_BRONZE
        # eligible = 20,000*3 = 60,000, no bonus applied -> 6 points
        assert customer.loyalty_points_balance == 6


# ── Reward catalog (browsable, vs. per-customer suggestions) ──────────

def test_reward_catalog_flags_suggested_items_and_sorts() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as database:
        near_expiry = _make_product(database, purchase_price="1", sale_price="5000", name="NearExpiry")
        near_expiry.expiration_date = datetime.now(UTC).date() + timedelta(days=5)
        near_expiry.stock_quantity = Decimal("10")
        database.commit()

        dead_stock = _make_product(database, purchase_price="1", sale_price="10000", name="DeadStock")
        dead_stock.stock_quantity = Decimal("10")
        database.commit()
        _seed_sale_history(database, dead_stock, days_ago=45)

        neither = _make_product(database, purchase_price="1", sale_price="3000", name="Neither")
        neither.stock_quantity = Decimal("10")
        database.commit()
        _seed_sale_history(database, neither, days_ago=5)

        rows = reward_catalog(database)
        by_id = {row["product_id"]: row for row in rows}
        assert by_id[near_expiry.id]["is_suggested"] is True
        assert by_id[dead_stock.id]["is_suggested"] is True
        assert by_id[neither.id]["is_suggested"] is False

        suggested_positions = [i for i, row in enumerate(rows) if row["is_suggested"]]
        unsuggested_positions = [i for i, row in enumerate(rows) if not row["is_suggested"]]
        assert max(suggested_positions) < min(unsuggested_positions)


def test_reward_catalog_search_filters_by_name() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as database:
        product_a = _make_product(database, purchase_price="1", sale_price="1000", name="Alpha Widget")
        product_b = _make_product(database, purchase_price="1", sale_price="1000", name="Beta Gadget")

        rows = reward_catalog(database, search="Widget")
        ids = {row["product_id"] for row in rows}
        assert product_a.id in ids
        assert product_b.id not in ids


# ── Loyalty redemption report (discounts/products given via points) ──

def test_loyalty_redemptions_report_shows_discount_and_products() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as database:
        customer = _make_customer(database)
        adjust_points_manually(database, customer, 10, reason="seed for test", user_id=None)
        product = _make_product(database, purchase_price="700", sale_price="1000", name="Redeemed Widget")

        sale = process_sale(
            database,
            SaleCreate(
                customer_id=customer.id,
                payment_method="credit",
                paid_amount=Decimal("0"),
                items=[SaleItemCreate(product_id=product.id, quantity=Decimal("100"))],
                redeem_points=6,  # 6 * 500 = 3,000 toman
            ),
        )

        rows = loyalty_redemptions(database)
        assert len(rows) == 1
        row = rows[0]
        assert row["customer_name"] == "Test Customer"
        assert row["invoice_number"] == sale.invoice_number
        assert row["discount_value"] == Decimal("3000.00")
        assert row["points_used"] == 6
        assert "Redeemed Widget" in row["product_names"]


def test_loyalty_redemptions_report_empty_when_no_redemptions() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as database:
        assert loyalty_redemptions(database) == []


def test_points_are_their_own_tender_bucket_and_never_reach_the_till() -> None:
    """A redemption settles part of an invoice without ever becoming a
    SalePaymentLine, so the tender report could not see it and quietly
    stopped adding up to revenue. It is a bucket now — but strictly on the
    reporting side: no points ever passed through the drawer, so the till
    must still ignore them."""
    from app.services.reports import payment_method_breakdown
    from app.services.shifts import close_shift, open_shift

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as database:
        product = Product(name="کالا", purchase_price=Decimal("1000"), sale_price=Decimal("10000"),
                          stock_quantity=Decimal("100"), low_stock_threshold=Decimal("0"), is_active=True)
        customer = Customer(full_name="عضو باشگاه", balance=Decimal("0"),
                            credit_limit=Decimal("0"), loyalty_member=True,
                            loyalty_points_balance=100)
        cashier = User(username="c", password_hash="x", full_name="صندوق‌دار", role="cashier")
        database.add_all([product, customer, cashier])
        database.commit()
        database.add(LoyaltyPointTransaction(customer_id=customer.id, points=100,
                                             transaction_type=LoyaltyTransactionType.EARN))
        database.commit()

        shift = open_shift(database, cashier_id=cashier.id, opening_cash=Decimal("0"))
        # 200,000 invoice: 20,000 on points (40 × 500), the rest in cash.
        sale = process_sale(database, SaleCreate(
            invoice_number="S-POINTS",
            customer_id=customer.id,
            items=[SaleItemCreate(product_id=product.id, quantity=Decimal("20"))],
            redeem_points=40,
            payment_lines=[SalePaymentLineInput(method="cash", amount=Decimal("180000"))]))
        assert sale.total == Decimal("200000.00")

        buckets = {row["payment_method"]: row["total"] for row in payment_method_breakdown(database)}
        assert buckets["loyalty"] == Decimal("20000.00"), "points settled part of the invoice"
        assert buckets["cash"] == Decimal("180000.00")
        assert sum(buckets.values()) == sale.total, "the breakdown reconciles to the sale again"

        closed = close_shift(database, shift, closing_cash=Decimal("180000"))
        assert closed.expected_cash == Decimal("180000.00"), (
            "only the cash reached the drawer — points are not money that moved"
        )
        assert closed.difference == Decimal("0.00")


def test_a_redemption_is_visible_to_whatever_prints_the_receipt() -> None:
    """Points settle part of an invoice without ever becoming a
    SalePaymentLine, so a receipt reading only payment_lines shows a split
    that does not add up to the total. Sale.loyalty_redeemed is what closes
    that gap, and SaleRead carries it."""
    from app.schemas.sale import SaleRead

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as database:
        product = Product(name="کالا", purchase_price=Decimal("1000"), sale_price=Decimal("10000"),
                          stock_quantity=Decimal("100"), low_stock_threshold=Decimal("0"), is_active=True)
        customer = Customer(full_name="عضو باشگاه", balance=Decimal("0"), credit_limit=Decimal("0"),
                            loyalty_member=True, loyalty_points_balance=100)
        database.add_all([product, customer])
        database.commit()
        database.add(LoyaltyPointTransaction(customer_id=customer.id, points=100,
                                             transaction_type=LoyaltyTransactionType.EARN))
        database.commit()

        sale = process_sale(database, SaleCreate(
            invoice_number="S-RECEIPT",
            customer_id=customer.id,
            items=[SaleItemCreate(product_id=product.id, quantity=Decimal("20"))],
            redeem_points=40,
            payment_lines=[SalePaymentLineInput(method="cash", amount=Decimal("180000"))]))

        assert sale.total == Decimal("200000.00")
        assert sale.loyalty_redeemed == Decimal("20000.00"), "40 points at 500 each"

        payload = SaleRead.model_validate(sale)
        tendered = sum(line.amount for line in payload.payment_lines) + payload.loyalty_redeemed
        assert tendered == payload.total, (
            "cash 180,000 + points 20,000 = the 200,000 invoice — a receipt built "
            "from payment_lines alone would have shown 180,000 against a 200,000 total"
        )
