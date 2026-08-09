"""باشگاه مشتریان (customer loyalty points program).

Design summary (see the task write-up for the full discussion):
- Points are earned only on money actually received — the single hook is
  called by every caller of financials.record_customer_payment() right
  after it runs (process_sale()'s initial payment, and the standalone
  POST /customers/{id}/payments route), never on unpaid credit balance.
- Each sale line's earn rate is proportional to its margin percentage
  (services/margin.py, ported from frontend/src/lib/margin.ts): a 10%
  margin line earns at the base rate, a 30% margin line earns 3x — a
  direct, continuous scale rather than the earlier 3-tier step function,
  per product-owner request. Zero/negative margin earns nothing.
- A line for a product that hasn't sold in DEAD_STOCK_LOOKBACK_DAYS (the
  same dead-stock signal services/reports.py::dead_stock() uses) earns an
  extra DEAD_STOCK_EARN_BOOST multiplier on top of its margin rate, to
  actively push customers toward buying down slow movers.
- A customer only earns points once they're a loyalty club member.
  Membership is automatic and immediate when no manager threshold is
  configured (LoyaltySettings both NULL) — matching the program's
  original design — but once a manager sets a minimum invoice total
  and/or minimum invoice profit, a customer becomes a member the moment
  one of their invoices reaches either figure (see _ensure_membership).
- 1 point per POINTS_PER_TOMAN of eligible paid revenue; fractional
  progress carries over via Customer.loyalty_progress_toman so several
  small payments don't lose value to rounding.
- Redemption converts points to a real CustomerPayment (method=LOYALTY)
  against a specific sale — capped at REDEMPTION_CAP_PCT of that
  invoice's total, and never more than the customer's available balance.
  This keeps the customer ledger, sale.paid_amount/remaining_amount, and
  customer.balance all correct with zero special-casing anywhere else
  that already reads those fields.
- Points expire POINT_EXPIRY_DAYS after being earned. There is no
  scheduler/cron in this codebase, so expiry is swept lazily — whenever a
  customer's balance is about to be read or touched (redemption, the
  points-liability report, a manual adjustment) rather than proactively.

Phase 3 additions:
- A manager can override the automatic per-line earn rate on a specific
  Product (`loyalty_point_multiplier`) — see _line_multiplier().
- reward_suggestions() surfaces which products a customer's current point
  balance could go toward, prioritizing near-expiry and dead-stock items —
  a read-only recommendation list. Redemption itself still happens through
  the existing flat cash-equivalent mechanic (redeem_points): a cashier
  adds the suggested product to the sale like any other line and redeems
  enough points to cover it. No separate "buy with points only" checkout
  path was built — the existing one already composes with this.
- customer_tier() classifies a customer as bronze/silver/gold based on
  lifetime completed-sale spend against two manager-configured thresholds
  (LoyaltySettings.tier_*_min_spend) — computed live on read, not stored,
  so it can never drift out of sync with actual sales history.
- issue_churn_recovery_coupons() is the "automated coupon issuance" this
  codebase can honestly support without a scheduler: a manager clicks a
  button, and every currently churn-risk customer who hasn't already
  gotten one within CHURN_RECOVERY_COOLDOWN_DAYS receives a bonus-point
  grant in one bulk action — automatic *selection*, manager-triggered
  *timing*.

Phase 4 additions:
- Tier-linked earn bonus: a silver/gold customer's whole computed earn
  value for a sale gets multiplied by LoyaltySettings.tier_*_earn_bonus
  (see _tier_earn_bonus) — a real functional perk for reaching a tier,
  not just a badge. Bronze never gets a bonus (1x, the base rate).
- reward_catalog() is the browsable counterpart to reward_suggestions():
  every active, in-stock product with its point cost, not just the
  customer-specific near-expiry/dead-stock subset — for a manager who
  wants to see the whole picture rather than per-customer suggestions.
"""

from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_CEILING, Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.store_time import business_day, business_day_now
from app.models.entities import (
    Customer,
    CustomerPayment,
    DocumentStatus,
    LoyaltyPointTransaction,
    LoyaltySettings,
    LoyaltyTransactionType,
    PaymentMethod,
    Product,
    Sale,
    SaleItem,
)
from app.services.financials import payment_status
from app.services.margin import calculate_margin_pct


class LoyaltyError(ValueError):
    pass


# ── Tunable program parameters — change here, nowhere else ──────────────
POINTS_PER_TOMAN = Decimal("10000")
POINT_VALUE_TOMAN = Decimal("500")
REDEMPTION_CAP_PCT = Decimal("0.30")
POINT_EXPIRY_DAYS = 365  # ~12 months

# Margin-proportional point weighting: margin_pct / MARGIN_MULTIPLIER_DIVISOR
# is the earn-rate multiplier, so e.g. a 10% margin line earns the base
# rate (1x) and a 30% margin line earns 3x. Zero/negative margin earns 0.
MARGIN_MULTIPLIER_DIVISOR = Decimal("10")

# A line for a product that hasn't sold in DEAD_STOCK_LOOKBACK_DAYS (or has
# never sold) earns DEAD_STOCK_EARN_BOOST times its margin-based rate.
DEAD_STOCK_LOOKBACK_DAYS = 30
DEAD_STOCK_EARN_BOOST = Decimal("2")


def _margin_multiplier(margin_pct: Decimal) -> Decimal:
    if margin_pct <= 0:
        return Decimal("0")
    return margin_pct / MARGIN_MULTIPLIER_DIVISOR


def _is_dead_stock(database: Session, product_id: int, *, exclude_sale_id: int | None) -> bool:
    """Whether `product_id` has had no completed sale in the last
    DEAD_STOCK_LOOKBACK_DAYS, ignoring `exclude_sale_id` (the sale
    currently being processed — it's already flushed as COMPLETED by the
    time this runs, so without the exclusion every line would look
    "just sold today" and never qualify for the boost it's meant to grant)."""
    query = (
        select(func.max(business_day(Sale.created_at)))
        .select_from(SaleItem)
        .join(Sale, Sale.id == SaleItem.sale_id)
        .where(SaleItem.product_id == product_id, Sale.status == DocumentStatus.COMPLETED)
    )
    if exclude_sale_id is not None:
        query = query.where(Sale.id != exclude_sale_id)
    last_sale_date = database.scalar(query)
    if last_sale_date is None:
        return True
    cutoff = business_day_now() - timedelta(days=DEAD_STOCK_LOOKBACK_DAYS)
    # business_day() is typed as a Date and hands back a real date; the old
    # func.date() returned an ISO string that had to be parsed here.
    return last_sale_date < cutoff


def _last_sale_dates(database: Session, product_ids: list[int]) -> dict[int, date]:
    """Batch version of _is_dead_stock's underlying lookup: one query for
    every product's most recent completed-sale date, instead of one query
    per product. Used by reward_suggestions()/reward_catalog(), which each
    need this signal for every product in the catalog — looping
    _is_dead_stock() per product there would be an N+1 query per request.
    """
    if not product_ids:
        return {}
    rows = database.execute(
        select(SaleItem.product_id, func.max(business_day(Sale.created_at)))
        .select_from(SaleItem)
        .join(Sale, Sale.id == SaleItem.sale_id)
        .where(SaleItem.product_id.in_(product_ids), Sale.status == DocumentStatus.COMPLETED)
        .group_by(SaleItem.product_id)
    ).all()
    return {product_id: last_date for product_id, last_date in rows}


def _is_dead_stock_from_map(last_sale_dates: dict[int, date], product_id: int) -> bool:
    last_sale_date = last_sale_dates.get(product_id)
    if last_sale_date is None:
        return True
    cutoff = business_day_now() - timedelta(days=DEAD_STOCK_LOOKBACK_DAYS)
    return last_sale_date < cutoff


def _line_multiplier(database: Session, item: SaleItem, sale_id: int) -> Decimal:
    """Override precedence: Product.loyalty_point_multiplier, then the
    automatic calculation. A product-level override replaces the automatic
    calculation outright (including the dead-stock boost — a manual figure
    is the manager's final word, not a floor to build on top of). Category
    has no say in loyalty points at all — category management is a plain
    catalog concept, kept fully decoupled from the loyalty program.
    """
    product = item.product
    if product.loyalty_point_multiplier is not None:
        return product.loyalty_point_multiplier

    margin_pct = calculate_margin_pct(item.unit_price, item.cost_price)
    if margin_pct is None:
        return Decimal("0")
    multiplier = _margin_multiplier(margin_pct)
    if multiplier <= 0:
        return Decimal("0")
    if _is_dead_stock(database, item.product_id, exclude_sale_id=sale_id):
        multiplier *= DEAD_STOCK_EARN_BOOST
    return multiplier


def _eligible_value(database: Session, sale: Sale) -> Decimal:
    """Sum of each line's line_total, weighted by its earn-rate multiplier
    (see _line_multiplier)."""
    total = Decimal("0")
    for item in sale.items:
        multiplier = _line_multiplier(database, item, sale.id)
        if multiplier <= 0:
            continue
        total += item.line_total * multiplier
    return total


def get_loyalty_settings(database: Session) -> LoyaltySettings:
    """The single-row (id=1) manager-configurable loyalty settings —
    created lazily with both thresholds disabled if the seed row is
    somehow missing (e.g. a pre-migration test database)."""
    settings_row = database.get(LoyaltySettings, 1)
    if settings_row is None:
        settings_row = LoyaltySettings(id=1)
        database.add(settings_row)
        database.flush()
    return settings_row


def update_loyalty_settings(
    database: Session,
    *,
    min_invoice_total: Decimal | None,
    min_invoice_profit: Decimal | None,
    user_id: int | None,
    tier_silver_min_spend: Decimal | None = None,
    tier_gold_min_spend: Decimal | None = None,
    tier_window_days: int | None = None,
    tier_silver_earn_bonus: Decimal | None = None,
    tier_gold_earn_bonus: Decimal | None = None,
    churn_recovery_coupon_points: int | None = None,
) -> LoyaltySettings:
    settings_row = get_loyalty_settings(database)
    settings_row.min_invoice_total_for_membership = min_invoice_total
    settings_row.min_invoice_profit_for_membership = min_invoice_profit
    settings_row.tier_silver_min_spend = tier_silver_min_spend
    settings_row.tier_gold_min_spend = tier_gold_min_spend
    settings_row.tier_window_days = tier_window_days
    settings_row.tier_silver_earn_bonus = tier_silver_earn_bonus
    settings_row.tier_gold_earn_bonus = tier_gold_earn_bonus
    settings_row.churn_recovery_coupon_points = churn_recovery_coupon_points
    settings_row.updated_by_user_id = user_id
    database.commit()
    database.refresh(settings_row)
    return settings_row


def _invoice_profit(sale: Sale) -> Decimal:
    total = Decimal("0")
    for item in sale.items:
        total += (item.unit_price - item.cost_price) * item.quantity
    return total


def _ensure_membership(database: Session, customer: Customer, sale: Sale) -> bool:
    """Manager-configurable auto-enrollment: a customer becomes a loyalty
    club member the moment one of their invoices reaches a configured
    minimum total or minimum profit. With no thresholds configured, every
    customer qualifies immediately — the original, threshold-free design.
    Mutates customer.loyalty_member in place; returns whether the customer
    is (now) a member, i.e. whether this call should go on to earn points.
    """
    if customer.loyalty_member:
        return True

    settings_row = get_loyalty_settings(database)
    if (
        settings_row.min_invoice_total_for_membership is None
        and settings_row.min_invoice_profit_for_membership is None
    ):
        customer.loyalty_member = True
        return True

    qualifies = (
        settings_row.min_invoice_total_for_membership is not None
        and sale.total >= settings_row.min_invoice_total_for_membership
    ) or (
        settings_row.min_invoice_profit_for_membership is not None
        and _invoice_profit(sale) >= settings_row.min_invoice_profit_for_membership
    )
    if qualifies:
        customer.loyalty_member = True
    return qualifies


def award_points_for_payment(
    database: Session, customer: Customer, sale: Sale | None, amount: Decimal
) -> None:
    """Call this right after financials.record_customer_payment() succeeds
    for a real (non-loyalty) payment. A no-op when `sale` is None (a
    payment not tied to a specific invoice) — with no line items to weigh
    by margin, no eligibility figure can be computed, so no points are
    invented on it. Also a no-op if the customer isn't a loyalty member
    yet and this sale doesn't qualify them for membership (see
    _ensure_membership).
    """
    if sale is None or sale.total <= 0 or amount <= 0:
        return
    if not _ensure_membership(database, customer, sale):
        return

    eligible_value = _eligible_value(database, sale)
    if eligible_value <= 0:
        return
    eligible_value *= _tier_earn_bonus(database, customer)
    paid_fraction = amount / sale.total
    eligible_amount = eligible_value * paid_fraction

    progress = customer.loyalty_progress_toman + eligible_amount
    points_earned = int(progress // POINTS_PER_TOMAN)
    customer.loyalty_progress_toman = progress - (points_earned * POINTS_PER_TOMAN)

    if points_earned > 0:
        customer.loyalty_points_balance += points_earned
        database.add(
            LoyaltyPointTransaction(
                customer_id=customer.id,
                points=points_earned,
                transaction_type=LoyaltyTransactionType.EARN,
                sale_id=sale.id,
                expires_at=datetime.now(UTC) + timedelta(days=POINT_EXPIRY_DAYS),
            )
        )


def sweep_expired_points(database: Session, customer: Customer) -> int:
    """Expire any EARN transaction whose expires_at has passed and hasn't
    been swept yet. Returns the number of points expired this call.
    """
    now = datetime.now(UTC)
    expired_rows = list(
        database.scalars(
            select(LoyaltyPointTransaction).where(
                LoyaltyPointTransaction.customer_id == customer.id,
                LoyaltyPointTransaction.transaction_type == LoyaltyTransactionType.EARN,
                LoyaltyPointTransaction.expired.is_(False),
                LoyaltyPointTransaction.expires_at.is_not(None),
                LoyaltyPointTransaction.expires_at < now,
            )
        )
    )
    total_expired = 0
    for row in expired_rows:
        row.expired = True
        total_expired += row.points
        database.add(
            LoyaltyPointTransaction(
                customer_id=customer.id,
                points=-row.points,
                transaction_type=LoyaltyTransactionType.EXPIRE,
                sale_id=row.sale_id,
            )
        )
    if total_expired > 0:
        customer.loyalty_points_balance = max(0, customer.loyalty_points_balance - total_expired)
    return total_expired


def max_redeemable_points(sale_total: Decimal, available_points: int) -> int:
    """What the frontend should treat as the redemption ceiling for a given
    invoice — the smaller of the customer's balance and the cap-derived
    point count. Exposed separately so the checkout UI can show it before
    the customer commits to a specific point amount.
    """
    if sale_total <= 0:
        return 0
    cap_value = sale_total * REDEMPTION_CAP_PCT
    cap_points = int(cap_value // POINT_VALUE_TOMAN)
    return max(0, min(available_points, cap_points))


def redeem_points(database: Session, customer: Customer, sale: Sale, points: int) -> Decimal:
    """Apply `points` worth of loyalty credit to `sale` as a real
    CustomerPayment (method=LOYALTY) — reduces remaining_amount and
    customer.balance exactly like a cash payment would, but is drawn from
    the point balance instead of the customer's wallet, and does not
    itself earn new points. Returns the toman value applied.
    """
    if points <= 0:
        return Decimal("0")
    sweep_expired_points(database, customer)
    if points > customer.loyalty_points_balance:
        raise LoyaltyError("Requested points exceed the customer's available balance")

    value = Decimal(points) * POINT_VALUE_TOMAN
    cap_value = sale.total * REDEMPTION_CAP_PCT
    if value > cap_value:
        raise LoyaltyError(
            f"Points redemption cannot exceed {REDEMPTION_CAP_PCT * 100}% of the invoice total"
        )
    if value > sale.remaining_amount:
        raise LoyaltyError("Points redemption cannot exceed the remaining amount due")

    database.add(
        CustomerPayment(
            customer=customer,
            sale=sale,
            amount=value,
            method=PaymentMethod.LOYALTY,
            reference=f"{points} امتیاز وفاداری",
        )
    )
    sale.paid_amount += value
    sale.remaining_amount = sale.total - sale.paid_amount
    sale.payment_status = payment_status(sale.total, sale.paid_amount)
    customer.balance = max(Decimal("0"), customer.balance - value)
    customer.loyalty_points_balance -= points
    database.add(
        LoyaltyPointTransaction(
            customer_id=customer.id,
            points=-points,
            transaction_type=LoyaltyTransactionType.REDEEM,
            sale_id=sale.id,
        )
    )
    return value


def adjust_points_manually(
    database: Session,
    customer: Customer,
    delta: int,
    *,
    reason: str,
    user_id: int | None,
) -> Customer:
    """Admin/manager manual correction — always requires a reason, always
    logged, mirroring every other sensitive manual action in this app
    (invoice edits, dual-price collapse, etc).
    """
    if not reason or not reason.strip():
        raise LoyaltyError("A reason is required for a manual point adjustment")
    sweep_expired_points(database, customer)
    new_balance = customer.loyalty_points_balance + delta
    if new_balance < 0:
        raise LoyaltyError("Adjustment would make the customer's point balance negative")

    customer.loyalty_points_balance = new_balance
    database.add(
        LoyaltyPointTransaction(
            customer_id=customer.id,
            points=delta,
            transaction_type=LoyaltyTransactionType.ADJUST,
            reason=reason.strip(),
            created_by_user_id=user_id,
        )
    )
    database.commit()
    database.refresh(customer)
    return customer


# ── Reward suggestions (dead-stock + near-expiry) ────────────────────────

NEAR_EXPIRY_DAYS = 14


def reward_suggestions(
    database: Session, customer: Customer, *, near_expiry_days: int = NEAR_EXPIRY_DAYS
) -> list[dict]:
    """Which products this customer's current point balance could go
    toward, instead of a flat cash-equivalent discount — prioritizing
    near-expiry stock (most urgent) then dead stock (by value tied up).
    Read-only: actual redemption still happens through redeem_points() at
    checkout, exactly as before — this only recommends what to add to the
    cart.
    """
    sweep_expired_points(database, customer)
    today = business_day_now()
    expiry_cutoff = today + timedelta(days=near_expiry_days)

    products = database.scalars(
        select(Product).where(Product.is_active.is_(True), Product.stock_quantity > 0)
    ).all()
    last_sale_dates = _last_sale_dates(database, [product.id for product in products])

    suggestions = []
    for product in products:
        near_expiry = product.expiration_date is not None and product.expiration_date <= expiry_cutoff
        dead_stock = _is_dead_stock_from_map(last_sale_dates, product.id)
        if not near_expiry and not dead_stock:
            continue
        points_required = int(
            (product.sale_price / POINT_VALUE_TOMAN).to_integral_value(rounding=ROUND_CEILING)
        )
        days_until_expiry = (product.expiration_date - today).days if near_expiry else None
        suggestions.append(
            {
                "product_id": product.id,
                "product_name": product.name,
                "sale_price": product.sale_price,
                "points_required": points_required,
                "affordable": points_required <= customer.loyalty_points_balance,
                "reason": "near_expiry" if near_expiry else "dead_stock",
                "days_until_expiry": days_until_expiry,
            }
        )

    suggestions.sort(
        key=lambda row: (
            0 if row["reason"] == "near_expiry" else 1,
            row["days_until_expiry"] if row["days_until_expiry"] is not None else 999_999,
        )
    )
    return suggestions


def reward_catalog(database: Session, *, search: str | None = None) -> list[dict]:
    """The browsable counterpart to reward_suggestions(): every active,
    in-stock product with its point cost, not filtered down to any one
    customer's near-expiry/dead-stock subset — for a manager who wants to
    see the whole picture, or a cashier browsing what's redeemable in
    general. Still flags is_suggested (near-expiry or dead-stock) so the
    priority items stand out without being the only things listed.
    """
    today = business_day_now()
    expiry_cutoff = today + timedelta(days=NEAR_EXPIRY_DAYS)

    query = select(Product).where(Product.is_active.is_(True), Product.stock_quantity > 0)
    if search:
        query = query.where(Product.name.ilike(f"%{search.strip()}%"))
    products = database.scalars(query.order_by(Product.name)).all()
    last_sale_dates = _last_sale_dates(database, [product.id for product in products])

    rows = []
    for product in products:
        near_expiry = product.expiration_date is not None and product.expiration_date <= expiry_cutoff
        dead_stock = _is_dead_stock_from_map(last_sale_dates, product.id)
        points_required = int(
            (product.sale_price / POINT_VALUE_TOMAN).to_integral_value(rounding=ROUND_CEILING)
        )
        rows.append(
            {
                "product_id": product.id,
                "product_name": product.name,
                "sale_price": product.sale_price,
                "points_required": points_required,
                "is_suggested": near_expiry or dead_stock,
                "reason": "near_expiry" if near_expiry else ("dead_stock" if dead_stock else None),
            }
        )
    rows.sort(key=lambda row: (0 if row["is_suggested"] else 1, row["points_required"]))
    return rows


# ── Customer tiers (bronze/silver/gold) ──────────────────────────────────

TIER_BRONZE = "bronze"
TIER_SILVER = "silver"
TIER_GOLD = "gold"


def _tier_spend(database: Session, customer_id: int, *, window_days: int | None) -> Decimal:
    """Completed-sale spend for tier classification. window_days=None means
    all-time/lifetime (the original behavior); otherwise only sales in the
    trailing window_days days count, so a customer who spent heavily long
    ago but hasn't been back recently doesn't stay gold forever."""
    query = select(func.coalesce(func.sum(Sale.total), 0)).where(
        Sale.customer_id == customer_id, Sale.status == DocumentStatus.COMPLETED
    )
    if window_days is not None:
        cutoff = datetime.now(UTC) - timedelta(days=window_days)
        query = query.where(Sale.created_at >= cutoff)
    return Decimal(database.scalar(query))


def classify_tier(spend: Decimal, settings_row: LoyaltySettings) -> str:
    """Pure bronze/silver/gold decision given a spend figure and the
    current settings — the single source of truth for tier thresholds, so
    customer_tier() (single customer) and reports.customer_tiers_report()
    (bulk) can never drift apart on what counts as silver/gold.
    """
    if settings_row.tier_gold_min_spend is not None and spend >= settings_row.tier_gold_min_spend:
        return TIER_GOLD
    if settings_row.tier_silver_min_spend is not None and spend >= settings_row.tier_silver_min_spend:
        return TIER_SILVER
    return TIER_BRONZE


def customer_tier(database: Session, customer: Customer) -> str:
    """Bronze/silver/gold, computed live from completed-sale spend (over
    LoyaltySettings.tier_window_days, or all-time if unset) against
    manager-configured thresholds — never stored, so it can never drift out
    of sync with actual sales history. Bronze (the base tier) needs no
    threshold and no spend lookup at all when tiers are disabled (both
    thresholds NULL).
    """
    settings_row = get_loyalty_settings(database)
    if settings_row.tier_gold_min_spend is None and settings_row.tier_silver_min_spend is None:
        return TIER_BRONZE

    spend = _tier_spend(database, customer.id, window_days=settings_row.tier_window_days)
    return classify_tier(spend, settings_row)


def _tier_earn_bonus(database: Session, customer: Customer) -> Decimal:
    """The multiplier a customer's tier applies on top of their whole
    computed earn value for a sale — a real functional perk for reaching a
    tier, not just a badge. Bronze (and any tier with no configured bonus)
    is 1x. Skips the tier lookup entirely (and its spend query) when
    neither bonus is configured, matching this feature's opt-in design.
    """
    settings_row = get_loyalty_settings(database)
    if settings_row.tier_silver_earn_bonus is None and settings_row.tier_gold_earn_bonus is None:
        return Decimal("1")

    tier = customer_tier(database, customer)
    if tier == TIER_GOLD and settings_row.tier_gold_earn_bonus is not None:
        return settings_row.tier_gold_earn_bonus
    if tier == TIER_SILVER and settings_row.tier_silver_earn_bonus is not None:
        return settings_row.tier_silver_earn_bonus
    return Decimal("1")


# ── Automated churn-recovery coupon issuance ─────────────────────────────

CHURN_RECOVERY_COOLDOWN_DAYS = 90
CHURN_RECOVERY_REASON = "کوپن بازگشت مشتری (خودکار)"


def issue_churn_recovery_coupons(database: Session, *, user_id: int | None) -> list[dict]:
    """Manager-triggered bulk action. This codebase has no scheduler, so
    "automated" here means algorithmic *selection*: every currently
    churn-risk customer (see reports.churn_risk_customers) who is already
    a loyalty member and hasn't received a churn-recovery coupon within
    CHURN_RECOVERY_COOLDOWN_DAYS gets a one-time bonus-point grant, all in
    one click rather than picking each customer by hand. A no-op (returns
    an empty list) when churn_recovery_coupon_points isn't configured.
    """
    settings_row = get_loyalty_settings(database)
    points = settings_row.churn_recovery_coupon_points
    if not points or points <= 0:
        return []

    from app.services.reports import churn_risk_customers  # deferred: avoids a circular import at module load

    at_risk = churn_risk_customers(database)
    if not at_risk:
        return []

    cooldown_cutoff = datetime.now(UTC) - timedelta(days=CHURN_RECOVERY_COOLDOWN_DAYS)
    issued = []
    for row in at_risk:
        customer = database.get(Customer, row["customer_id"])
        if customer is None or not customer.loyalty_member:
            continue
        already_issued = database.scalar(
            select(LoyaltyPointTransaction.id).where(
                LoyaltyPointTransaction.customer_id == customer.id,
                LoyaltyPointTransaction.transaction_type == LoyaltyTransactionType.ADJUST,
                LoyaltyPointTransaction.reason == CHURN_RECOVERY_REASON,
                LoyaltyPointTransaction.created_at >= cooldown_cutoff,
            )
        )
        if already_issued is not None:
            continue

        customer.loyalty_points_balance += points
        database.add(
            LoyaltyPointTransaction(
                customer_id=customer.id,
                points=points,
                transaction_type=LoyaltyTransactionType.ADJUST,
                reason=CHURN_RECOVERY_REASON,
                created_by_user_id=user_id,
            )
        )
        issued.append({"customer_id": customer.id, "customer_name": customer.full_name, "points": points})

    if issued:
        database.commit()
    return issued
