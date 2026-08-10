from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.orm import selectinload

from app.core.store_time import business_day, business_day_bounds, business_day_now
from app.models.entities import (
    AuditLog, CashierShift, Category, Customer, CustomerPayment, DocumentStatus, PaymentMethod,
    Product, Purchase, PurchaseItem, Sale, SaleItem, SalePaymentLine, Supplier, User,
)
from app.services.expenses import total_operating_expenses


def daily_sales_summary(
    database: Session,
    *,
    from_date: date | None = None,
    to_date: date | None = None,
) -> list[dict]:
    today = business_day_now()
    from_date = from_date or today - timedelta(days=30)
    to_date = to_date or today
    sale_rows = (
        select(
            Sale.id.label("sale_id"),
            business_day(Sale.created_at).label("sale_date"),
            Sale.total,
            Sale.discount,
        )
        .where(
            Sale.status == DocumentStatus.COMPLETED,
            business_day(Sale.created_at) >= from_date,
            business_day(Sale.created_at) <= to_date,
        )
        .subquery()
    )

    sales_summary = (
        select(
            sale_rows.c.sale_date.label("sale_date"),
            func.coalesce(func.sum(sale_rows.c.total), 0).label("total_sales"),
            func.count(sale_rows.c.sale_id).label("transaction_count"),
            # Summed here, not in profit_summary below: that one joins
            # SaleItem, so a per-sale figure would be counted once per line.
            func.coalesce(func.sum(sale_rows.c.discount), 0).label("total_discount"),
        )
        .group_by(sale_rows.c.sale_date)
        .subquery()
    )

    profit_summary = (
        select(
            sale_rows.c.sale_date.label("sale_date"),
            func.coalesce(
                func.sum(SaleItem.line_total - (SaleItem.cost_price * SaleItem.quantity)),
                0,
            ).label("profit"),
        )
        .join(SaleItem, SaleItem.sale_id == sale_rows.c.sale_id)
        .group_by(sale_rows.c.sale_date)
        .subquery()
    )

    rows = database.execute(
        select(
            sales_summary.c.sale_date,
            sales_summary.c.total_sales,
            sales_summary.c.transaction_count,
            # SaleItem.line_total already nets off any per-item discount, but
            # the invoice-level discount lives on Sale and was never taken
            # off. Revenue (SUM of Sale.total) *does* subtract it, so profit
            # came out higher than revenue minus cost — a shop giving a
            # whole-invoice discount saw a profit it had not actually made,
            # and net_profit() inherited the error through this column.
            (
                func.coalesce(profit_summary.c.profit, Decimal("0"))
                - sales_summary.c.total_discount
            ).label("profit"),
        )
        .outerjoin(
            profit_summary,
            sales_summary.c.sale_date == profit_summary.c.sale_date,
        )
        .order_by(sales_summary.c.sale_date)
    ).all()
    return [
        {
            "date": row.sale_date,
            "total_sales": row[1],
            "transaction_count": row[2],
            "profit": row[3] or Decimal("0"),
            "average_ticket": row[1] / row[2] if row[2] > 0 else Decimal("0"),
        }
        for row in rows
    ]


def top_products(
    database: Session, *, limit: int = 20, sort_by: str = "revenue"
) -> list[dict]:
    quantity_sum = func.sum(SaleItem.quantity)
    revenue_sum = func.sum(SaleItem.line_total)
    profit_sum = func.sum(SaleItem.line_total - (SaleItem.cost_price * SaleItem.quantity))
    order_column = {
        "quantity": quantity_sum,
        "profit": profit_sum,
        "revenue": revenue_sum,
    }.get(sort_by, revenue_sum)

    rows = database.execute(
        select(
            SaleItem.product_id,
            Product.name,
            func.coalesce(quantity_sum, 0),
            func.coalesce(revenue_sum, 0),
            func.coalesce(profit_sum, 0),
        )
        .join(Product)
        .join(Sale)
        .where(Sale.status == DocumentStatus.COMPLETED)
        .group_by(SaleItem.product_id, Product.name)
        .order_by(order_column.desc())
        .limit(limit)
    ).all()
    return [
        {
            "product_id": row.product_id,
            "product_name": row.name,
            "total_quantity": row[2],
            "total_revenue": row[3],
            "total_profit": row[4] or Decimal("0"),
        }
        for row in rows
    ]


def payment_method_breakdown(
    database: Session,
    *,
    from_date: date | None = None,
    to_date: date | None = None,
) -> list[dict]:
    """Money collected per real tender (cash/card/check/credit) in the date
    range. A split-payment sale (Sale.payment_method == "mixed") is never its
    own bucket here — its total is distributed across its actual
    SalePaymentLine rows, so "mixed" never appears in the result. Sales with
    no payment lines at all (pure-credit sales, or rows predating the
    split-payment feature) fall back to their whole Sale.total under
    Sale.payment_method, same as before this changed.
    """
    today = business_day_now()
    from_date = from_date or today - timedelta(days=30)
    to_date = to_date or today
    date_filters = (
        Sale.status == DocumentStatus.COMPLETED,
        business_day(Sale.created_at) >= from_date,
        business_day(Sale.created_at) <= to_date,
    )

    # Sales that recorded actual tender lines: split by real payment method.
    line_rows = database.execute(
        select(
            SalePaymentLine.method,
            func.coalesce(func.sum(SalePaymentLine.amount), 0),
            func.count(SalePaymentLine.id),
        )
        .join(Sale, Sale.id == SalePaymentLine.sale_id)
        .where(*date_filters)
        .group_by(SalePaymentLine.method)
    ).all()

    # Sales with no payment lines (pure credit, or pre-split-payment legacy
    # rows): bucket the whole total under Sale.payment_method.
    lineless_rows = database.execute(
        select(
            Sale.payment_method,
            func.coalesce(func.sum(Sale.total), 0),
            func.count(Sale.id),
        )
        .where(*date_filters, Sale.id.notin_(select(SalePaymentLine.sale_id)))
        .group_by(Sale.payment_method)
    ).all()

    totals: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    counts: dict[str, int] = defaultdict(int)
    for method, total, count in [*line_rows, *lineless_rows]:
        key = method.value if hasattr(method, "value") else method
        totals[key] += total
        counts[key] += count

    return [
        {"payment_method": key, "total": totals[key], "transaction_count": counts[key]}
        for key in sorted(totals, key=lambda k: totals[k], reverse=True)
    ]


def low_stock(database: Session) -> list[dict]:
    products = database.scalars(
        select(Product)
        .where(
            Product.is_active.is_(True),
            Product.stock_quantity <= Product.low_stock_threshold,
        )
        .order_by(Product.stock_quantity)
    ).all()
    return [
        {
            "product_id": p.id,
            "product_name": p.name,
            "stock_quantity": p.stock_quantity,
            "low_stock_threshold": p.low_stock_threshold,
        }
        for p in products
    ]


def inventory_summary(database: Session) -> list[dict]:
    products = database.scalars(
        select(Product)
        .where(Product.is_active.is_(True))
        .order_by(Product.name)
    ).all()
    return [
        {
            "product_id": p.id,
            "product_name": p.name,
            "stock_quantity": p.stock_quantity,
            "purchase_price": p.purchase_price,
            "sale_price": p.sale_price,
            "estimated_value": p.stock_quantity * p.purchase_price,
            "total_stock_value": p.stock_quantity * p.purchase_price,
            "potential_profit": (p.stock_quantity * (p.sale_price - p.purchase_price)),
        }
        for p in products
    ]


def dead_stock(database: Session, *, lookback_days: int = 30) -> list[dict]:
    """Products with stock on hand that haven't sold within `lookback_days`
    (or have never sold at all). Zero-stock products are excluded — they
    aren't tying up capital regardless of how long it's been since they sold.
    """
    today = business_day_now()
    cutoff = today - timedelta(days=lookback_days)

    last_sale = (
        select(
            SaleItem.product_id.label("product_id"),
            func.max(business_day(Sale.created_at)).label("last_sale_date"),
        )
        .join(Sale, Sale.id == SaleItem.sale_id)
        .where(Sale.status == DocumentStatus.COMPLETED)
        .group_by(SaleItem.product_id)
        .subquery()
    )

    rows = database.execute(
        select(
            Product.id,
            Product.name,
            Category.name,
            Product.stock_quantity,
            Product.purchase_price,
            last_sale.c.last_sale_date,
        )
        .outerjoin(Category, Product.category_id == Category.id)
        .outerjoin(last_sale, last_sale.c.product_id == Product.id)
        .where(Product.is_active.is_(True), Product.stock_quantity > 0)
    ).all()

    result = []
    for product_id, product_name, category_name, stock_quantity, purchase_price, last_sale_date in rows:
        if last_sale_date is not None:
            if last_sale_date >= cutoff:
                continue
            days_since_last_sale = (today - last_sale_date).days
        else:
            days_since_last_sale = None

        result.append(
            {
                "product_id": product_id,
                "product_name": product_name,
                "category_name": category_name,
                "stock_quantity": stock_quantity,
                "days_since_last_sale": days_since_last_sale,
                "value_tied_up": stock_quantity * purchase_price,
            }
        )

    result.sort(key=lambda item: item["value_tied_up"], reverse=True)
    return result


def near_expiry_products(
    database: Session, *, red_days: int = 7, orange_days: int = 30
) -> list[dict]:
    """Products with stock on hand whose Product.expiration_date is already
    past, or falls within `orange_days` from today — a focused "needs
    attention" list, same shape as dead_stock() above, not a full inventory
    dump. Items expiring further out than orange_days simply aren't
    included, same as dead_stock excludes recently-sold products.

    Product.expiration_date (not PurchaseItem.expiry_date) is the
    authoritative source — it's the only expiry field any existing business
    logic (services/loyalty.py's near-expiry earn-rate boost) actually
    reads. PurchaseItem.expiry_date is recorded per purchase batch but never
    aggregated back onto the product, so there is nothing to reconcile here.
    Entirely independent of the loyalty near-expiry check — this function
    shares no code or threshold with services/loyalty.py.
    """
    today = business_day_now()
    orange_cutoff = today + timedelta(days=orange_days)

    rows = database.execute(
        select(Product.id, Product.name, Product.stock_quantity, Product.expiration_date)
        .where(
            Product.is_active.is_(True),
            Product.stock_quantity > 0,
            Product.expiration_date.is_not(None),
            Product.expiration_date <= orange_cutoff,
        )
    ).all()

    result = []
    for product_id, product_name, stock_quantity, expiration_date in rows:
        days_until_expiry = (expiration_date - today).days
        if days_until_expiry < 0:
            status = "expired"
        elif days_until_expiry <= red_days:
            status = "red"
        else:
            status = "orange"
        result.append(
            {
                "product_id": product_id,
                "product_name": product_name,
                "stock_quantity": stock_quantity,
                "expiration_date": expiration_date,
                "days_until_expiry": days_until_expiry,
                "status": status,
            }
        )

    # Most urgent first: already-expired (most negative days) before
    # soon-to-expire, mirroring dead_stock's "worst offender first" sort.
    result.sort(key=lambda item: item["days_until_expiry"])
    return result


def cashier_performance(
    database: Session,
    *,
    from_date: date | None = None,
    to_date: date | None = None,
) -> list[dict]:
    """Per-cashier aggregates for completed sales attributed via
    Sale.shift_id -> CashierShift.cashier_id — deliberately NOT via
    AuditLog.user_id, which records whoever was authenticated for the
    request rather than the cashier working that till: a manager editing an
    invoice would otherwise be counted as the one who rang it up. "Refund
    amount" from the original spec is omitted entirely: this codebase has
    no sales-refund/return concept at all, and fabricating a zero would
    violate the "no calculated fake values" requirement.
    """
    today = business_day_now()
    from_date = from_date or today - timedelta(days=30)
    to_date = to_date or today

    sale_rows = database.execute(
        select(
            CashierShift.cashier_id,
            User.full_name,
            func.count(Sale.id),
            func.coalesce(func.sum(Sale.total), 0),
            func.coalesce(func.sum(Sale.discount), 0),
        )
        .select_from(Sale)
        .join(CashierShift, Sale.shift_id == CashierShift.id)
        .join(User, CashierShift.cashier_id == User.id)
        .where(
            Sale.status == DocumentStatus.COMPLETED,
            business_day(Sale.created_at) >= from_date,
            business_day(Sale.created_at) <= to_date,
        )
        .group_by(CashierShift.cashier_id, User.full_name)
    ).all()

    # Same "split by actual tender, fall back to Sale.payment_method for
    # lineless sales" logic as reports.payment_method_breakdown() (see there
    # for why), just also grouped by cashier. Kept as a separate query rather
    # than calling that function because this one needs the CashierShift
    # join for per-cashier grouping.
    method_line_rows = database.execute(
        select(
            CashierShift.cashier_id,
            SalePaymentLine.method,
            func.coalesce(func.sum(SalePaymentLine.amount), 0),
        )
        .select_from(SalePaymentLine)
        .join(Sale, Sale.id == SalePaymentLine.sale_id)
        .join(CashierShift, Sale.shift_id == CashierShift.id)
        .where(
            Sale.status == DocumentStatus.COMPLETED,
            business_day(Sale.created_at) >= from_date,
            business_day(Sale.created_at) <= to_date,
        )
        .group_by(CashierShift.cashier_id, SalePaymentLine.method)
    ).all()
    method_lineless_rows = database.execute(
        select(
            CashierShift.cashier_id,
            Sale.payment_method,
            func.coalesce(func.sum(Sale.total), 0),
        )
        .select_from(Sale)
        .join(CashierShift, Sale.shift_id == CashierShift.id)
        .where(
            Sale.status == DocumentStatus.COMPLETED,
            business_day(Sale.created_at) >= from_date,
            business_day(Sale.created_at) <= to_date,
            Sale.id.notin_(select(SalePaymentLine.sale_id)),
        )
        .group_by(CashierShift.cashier_id, Sale.payment_method)
    ).all()
    breakdown_by_cashier: dict[int, dict[str, Decimal]] = defaultdict(dict)
    for cashier_id, method, total in [*method_line_rows, *method_lineless_rows]:
        key = method.value if hasattr(method, "value") else method
        per_cashier = breakdown_by_cashier[cashier_id]
        per_cashier[key] = per_cashier.get(key, Decimal("0")) + total

    # Held/edited/discarded counts: joined through the sale each audit entry
    # refers to, then through that sale's shift — NOT through
    # AuditLog.user_id, for the same reason as above: it names the
    # authenticated actor, not the cashier whose till the sale belongs to.
    action_rows = database.execute(
        select(
            CashierShift.cashier_id,
            AuditLog.action,
            func.count(AuditLog.id),
        )
        .select_from(AuditLog)
        .join(Sale, Sale.id == AuditLog.entity_id)
        .join(CashierShift, Sale.shift_id == CashierShift.id)
        .where(
            AuditLog.entity_type == "sale",
            AuditLog.action.in_(["edit", "hold", "resume", "discard"]),
            business_day(AuditLog.occurred_at) >= from_date,
            business_day(AuditLog.occurred_at) <= to_date,
        )
        .group_by(CashierShift.cashier_id, AuditLog.action)
    ).all()
    actions_by_cashier: dict[int, dict[str, int]] = defaultdict(dict)
    for cashier_id, action, count in action_rows:
        actions_by_cashier[cashier_id][action] = count

    result = []
    for cashier_id, full_name, invoice_count, total_sales, total_discount in sale_rows:
        actions = actions_by_cashier.get(cashier_id, {})
        result.append(
            {
                "cashier_id": cashier_id,
                "cashier_name": full_name,
                "invoice_count": invoice_count,
                "total_sales": total_sales,
                "average_ticket": (total_sales / invoice_count) if invoice_count else Decimal("0"),
                "total_discount": total_discount,
                "payment_method_breakdown": breakdown_by_cashier.get(cashier_id, {}),
                "edited_count": actions.get("edit", 0),
                "held_count": actions.get("hold", 0),
                "discarded_count": actions.get("discard", 0),
            }
        )
    result.sort(key=lambda row: row["total_sales"], reverse=True)
    return result


def customer_balances(database: Session) -> list[dict]:
    customers = database.scalars(
        select(Customer)
        .where(Customer.is_active.is_(True), Customer.balance > 0)
        .order_by(Customer.balance.desc())
    ).all()
    return [
        {
            "customer_id": c.id,
            "customer_name": c.full_name,
            "balance": c.balance,
            "credit_limit": c.credit_limit,
        }
        for c in customers
    ]


def loyalty_liability(database: Session) -> list[dict]:
    """Mirrors customer_balances() in shape/intent, but for the loyalty
    program: total point value outstanding is a future obligation the shop
    owner should be aware of, exactly like receivables/payables. Sweeps
    expired points for every customer first so the figure is current, not
    stale — matching Session.commit() usage elsewhere in this module's
    write-adjacent helpers.
    """
    from app.services.loyalty import POINT_VALUE_TOMAN, sweep_expired_points

    customers = database.scalars(
        select(Customer).where(Customer.is_active.is_(True), Customer.loyalty_points_balance > 0)
    ).all()
    swept_any = False
    for customer in customers:
        if sweep_expired_points(database, customer) > 0:
            swept_any = True
    if swept_any:
        database.commit()

    return [
        {
            "customer_id": c.id,
            "customer_name": c.full_name,
            "points_balance": c.loyalty_points_balance,
            "points_value_toman": Decimal(c.loyalty_points_balance) * POINT_VALUE_TOMAN,
        }
        for c in customers
        if c.loyalty_points_balance > 0
    ]


def loyalty_redemptions(
    database: Session,
    *,
    from_date: date | None = None,
    to_date: date | None = None,
) -> list[dict]:
    """Every point redemption (a CustomerPayment with method=LOYALTY) — the
    discount actually given via points, and what was bought on that
    invoice. Unlike loyalty_liability() (an outstanding-balance snapshot),
    this is activity history — what Reports keeps directly now that the
    rest of the loyalty program's tools live in the dedicated باشگاه
    مشتریان page instead.
    """
    from app.services.loyalty import POINT_VALUE_TOMAN

    query = (
        select(CustomerPayment)
        .where(CustomerPayment.method == PaymentMethod.LOYALTY)
        .options(
            selectinload(CustomerPayment.customer),
            selectinload(CustomerPayment.sale).selectinload(Sale.items).selectinload(SaleItem.product),
        )
        .order_by(CustomerPayment.paid_at.desc())
    )
    if from_date:
        query = query.where(CustomerPayment.paid_at >= business_day_bounds(from_date)[0])
    if to_date:
        query = query.where(CustomerPayment.paid_at < business_day_bounds(to_date)[1])

    payments = database.scalars(query).all()

    result = []
    for payment in payments:
        sale = payment.sale
        result.append(
            {
                "payment_id": payment.id,
                "customer_id": payment.customer_id,
                "customer_name": payment.customer.full_name if payment.customer else "",
                "sale_id": sale.id if sale else None,
                "invoice_number": sale.invoice_number if sale else None,
                "discount_value": payment.amount,
                "points_used": int(payment.amount / POINT_VALUE_TOMAN),
                "product_names": [item.product.name for item in sale.items] if sale else [],
                "paid_at": payment.paid_at,
            }
        )
    return result


def upcoming_birthdays(database: Session, *, within_days: int = 30) -> list[dict]:
    """Customers with a birth_date on file whose birthday falls within the
    next `within_days` days (wrapping year-end correctly). No automated
    messaging exists in this codebase — this is a visible list for a
    manager to act on manually, matching the low-stock widget's pattern.
    """
    today = business_day_now()
    customers = database.scalars(
        select(Customer).where(Customer.is_active.is_(True), Customer.birth_date.is_not(None))
    ).all()

    result = []
    for customer in customers:
        bday = customer.birth_date
        next_birthday = bday.replace(year=today.year)
        if next_birthday < today:
            next_birthday = bday.replace(year=today.year + 1)
        days_until = (next_birthday - today).days
        if days_until <= within_days:
            result.append(
                {
                    "customer_id": customer.id,
                    "customer_name": customer.full_name,
                    "phone": customer.phone,
                    "birth_date": customer.birth_date,
                    "days_until_birthday": days_until,
                }
            )
    result.sort(key=lambda row: row["days_until_birthday"])
    return result


def churn_risk_customers(
    database: Session,
    *,
    recent_window_days: int = 90,
    inactive_days: int = 30,
    min_recent_purchases: int = 2,
) -> list[dict]:
    """Customers who used to buy regularly (>= min_recent_purchases
    completed sales in the recent_window_days before their inactive
    window) but haven't purchased in the last inactive_days — i.e. someone
    worth a manual follow-up call, not someone who was never a regular.
    """
    now = datetime.now(UTC)
    recent_cutoff = now - timedelta(days=recent_window_days)
    inactive_cutoff = now - timedelta(days=inactive_days)

    rows = database.execute(
        select(
            Sale.customer_id,
            func.count(Sale.id).filter(Sale.created_at >= recent_cutoff, Sale.created_at < inactive_cutoff).label("recent_count"),
            func.max(Sale.created_at).label("last_purchase_at"),
        )
        .where(Sale.status == DocumentStatus.COMPLETED, Sale.customer_id.is_not(None))
        .group_by(Sale.customer_id)
        .having(func.max(Sale.created_at) < inactive_cutoff)
    ).all()

    customer_ids = [row.customer_id for row in rows if row.recent_count >= min_recent_purchases]
    if not customer_ids:
        return []
    customers = {
        c.id: c
        for c in database.scalars(
            select(Customer).where(Customer.id.in_(customer_ids), Customer.is_active.is_(True))
        )
    }

    result = []
    for row in rows:
        customer = customers.get(row.customer_id)
        if customer is None or row.recent_count < min_recent_purchases:
            continue
        last_purchase_at = row.last_purchase_at
        if last_purchase_at.tzinfo is None:
            last_purchase_at = last_purchase_at.replace(tzinfo=UTC)
        result.append(
            {
                "customer_id": customer.id,
                "customer_name": customer.full_name,
                "phone": customer.phone,
                "purchase_count_recent": row.recent_count,
                "last_purchase_at": last_purchase_at,
                "days_since_last_purchase": (now - last_purchase_at).days,
            }
        )
    result.sort(key=lambda row: row["days_since_last_purchase"], reverse=True)
    return result


def customer_tiers_report(database: Session) -> list[dict]:
    """Bronze/silver/gold classification per customer, based on completed-
    sale spend (over LoyaltySettings.tier_window_days, or all-time if
    unset) against the manager-configured thresholds — see
    services/loyalty.py::customer_tier()/classify_tier(), the single
    source of truth this report defers to so it can never classify a
    customer differently than their own detail page would. Only customers
    with at least one qualifying completed sale are listed (a customer
    with no purchase history yet isn't meaningfully "bronze", just new).
    Returns [] outright when tiers aren't configured (both thresholds
    NULL), matching this feature's opt-in design.
    """
    from app.services.loyalty import classify_tier, get_loyalty_settings

    settings_row = get_loyalty_settings(database)
    if settings_row.tier_gold_min_spend is None and settings_row.tier_silver_min_spend is None:
        return []

    query = select(Sale.customer_id, func.sum(Sale.total).label("spend")).where(
        Sale.status == DocumentStatus.COMPLETED, Sale.customer_id.is_not(None)
    )
    if settings_row.tier_window_days is not None:
        cutoff = datetime.now(UTC) - timedelta(days=settings_row.tier_window_days)
        query = query.where(Sale.created_at >= cutoff)
    rows = database.execute(query.group_by(Sale.customer_id)).all()
    if not rows:
        return []

    customer_ids = [row.customer_id for row in rows]
    customers = {
        c.id: c
        for c in database.scalars(
            select(Customer).where(Customer.id.in_(customer_ids), Customer.is_active.is_(True))
        )
    }

    result = []
    for row in rows:
        customer = customers.get(row.customer_id)
        if customer is None:
            continue
        spend = row.spend or Decimal("0")
        result.append(
            {
                "customer_id": customer.id,
                "customer_name": customer.full_name,
                "lifetime_spend": spend,
                "tier": classify_tier(spend, settings_row),
            }
        )

    tier_rank = {"gold": 0, "silver": 1, "bronze": 2}
    result.sort(key=lambda r: (tier_rank[r["tier"]], -r["lifetime_spend"]))
    return result


def supplier_balances(database: Session) -> list[dict]:
    suppliers = database.scalars(
        select(Supplier)
        .where(Supplier.is_active.is_(True), Supplier.balance > 0)
        .order_by(Supplier.balance.desc())
    ).all()
    return [
        {
            "supplier_id": s.id,
            "supplier_name": s.name,
            "balance": s.balance,
            "credit_limit": s.credit_limit,
        }
        for s in suppliers
    ]


# ─────────────────────────────────────────────────────────────────────────
# Internal inflation-rate report — see docs/inflation-rate-report.md for the
# full spec (formulas, edge cases, UX layout). This is an internal pricing
# signal derived purely from this store's own purchase/sale history between
# two user-chosen periods — explicitly NOT an official/national inflation
# rate. Every function below reads from the one shared _inflation_raw_data()
# grouped dataset; nothing here re-queries PurchaseItem/SaleItem.
# ─────────────────────────────────────────────────────────────────────────

# "موارد استثنا": below this many products transacted in *both* periods, an
# index is statistically meaningless — return None (insufficient data)
# instead of a number, store-wide and independently per category.
MIN_COMMON_PRODUCTS = 5


@dataclass
class _ProductPeriodRow:
    """One product's raw purchase/sale quantity+value in each of the two
    periods — the shared grouped dataset every index function below reads.
    Cost/revenue are 0 (not None) when there was no activity that period/side,
    so "common product" checks are simple `> 0` comparisons.
    """

    product_id: int
    product_name: str
    category_id: int | None
    category_name: str | None
    purchase_qty_p1: Decimal
    purchase_cost_p1: Decimal
    purchase_qty_p2: Decimal
    purchase_cost_p2: Decimal
    sale_qty_p1: Decimal
    sale_revenue_p1: Decimal
    sale_qty_p2: Decimal
    sale_revenue_p2: Decimal


def _period_purchase_agg(database: Session, start: date, end: date) -> dict[int, tuple[Decimal, Decimal]]:
    """product_id -> (total_qty, total_cost) from completed, non-zero-cost
    purchase lines in [start, end] — "موارد استثنا" excludes zero-cost lines
    since their price isn't a real market price.
    """
    rows = database.execute(
        select(
            PurchaseItem.product_id,
            func.sum(PurchaseItem.quantity),
            func.sum(PurchaseItem.quantity * PurchaseItem.unit_cost),
        )
        .join(Purchase, Purchase.id == PurchaseItem.purchase_id)
        .where(
            Purchase.status == DocumentStatus.COMPLETED,
            PurchaseItem.unit_cost > 0,
            business_day(Purchase.created_at) >= start,
            business_day(Purchase.created_at) <= end,
        )
        .group_by(PurchaseItem.product_id)
    ).all()
    return {row[0]: (row[1], row[2]) for row in rows}


def _period_sale_agg(database: Session, start: date, end: date) -> dict[int, tuple[Decimal, Decimal]]:
    """product_id -> (total_qty, total_revenue) from completed sale lines in
    [start, end]."""
    rows = database.execute(
        select(
            SaleItem.product_id,
            func.sum(SaleItem.quantity),
            func.sum(SaleItem.quantity * SaleItem.unit_price),
        )
        .join(Sale, Sale.id == SaleItem.sale_id)
        .where(
            Sale.status == DocumentStatus.COMPLETED,
            business_day(Sale.created_at) >= start,
            business_day(Sale.created_at) <= end,
        )
        .group_by(SaleItem.product_id)
    ).all()
    return {row[0]: (row[1], row[2]) for row in rows}


def _inflation_raw_data(
    database: Session,
    period1_start: date,
    period1_end: date,
    period2_start: date,
    period2_end: date,
) -> list[_ProductPeriodRow]:
    purchase_p1 = _period_purchase_agg(database, period1_start, period1_end)
    purchase_p2 = _period_purchase_agg(database, period2_start, period2_end)
    sale_p1 = _period_sale_agg(database, period1_start, period1_end)
    sale_p2 = _period_sale_agg(database, period2_start, period2_end)

    product_ids = set(purchase_p1) | set(purchase_p2) | set(sale_p1) | set(sale_p2)
    if not product_ids:
        return []

    zero = Decimal("0")
    products = database.execute(
        select(Product.id, Product.name, Product.category_id, Category.name)
        .outerjoin(Category, Product.category_id == Category.id)
        .where(Product.id.in_(product_ids))
    ).all()

    rows = []
    for product_id, product_name, category_id, category_name in products:
        pq1, pc1 = purchase_p1.get(product_id, (zero, zero))
        pq2, pc2 = purchase_p2.get(product_id, (zero, zero))
        sq1, sr1 = sale_p1.get(product_id, (zero, zero))
        sq2, sr2 = sale_p2.get(product_id, (zero, zero))
        rows.append(
            _ProductPeriodRow(
                product_id=product_id,
                product_name=product_name,
                category_id=category_id,
                category_name=category_name,
                purchase_qty_p1=pq1,
                purchase_cost_p1=pc1,
                purchase_qty_p2=pq2,
                purchase_cost_p2=pc2,
                sale_qty_p1=sq1,
                sale_revenue_p1=sr1,
                sale_qty_p2=sq2,
                sale_revenue_p2=sr2,
            )
        )
    return rows


def _common_purchase_rows(rows: list[_ProductPeriodRow]) -> list[_ProductPeriodRow]:
    """Cost-side "apples to apples" set: a purchase in *both* periods."""
    return [r for r in rows if r.purchase_qty_p1 > 0 and r.purchase_qty_p2 > 0]


def _common_sale_rows(rows: list[_ProductPeriodRow]) -> list[_ProductPeriodRow]:
    """Sale-side "apples to apples" set: a sale in *both* periods."""
    return [r for r in rows if r.sale_qty_p1 > 0 and r.sale_qty_p2 > 0]


def price_index(rows: list[_ProductPeriodRow], *, basis: str) -> Decimal | None:
    """Laspeyres price index, weighted by period-1 quantity (see "روش درست"
    in the doc) — basis="cost" reads PurchaseItem.unit_cost, basis="price"
    reads SaleItem.unit_price. Returns the raw ~100-based index (100 = no
    change); None when fewer than MIN_COMMON_PRODUCTS qualify.
    """
    common = _common_purchase_rows(rows) if basis == "cost" else _common_sale_rows(rows)
    if len(common) < MIN_COMMON_PRODUCTS:
        return None

    if basis == "cost":
        denominator = sum((r.purchase_cost_p1 for r in common), Decimal("0"))
        numerator = sum(
            ((r.purchase_cost_p2 / r.purchase_qty_p2) * r.purchase_qty_p1 for r in common),
            Decimal("0"),
        )
    else:
        denominator = sum((r.sale_revenue_p1 for r in common), Decimal("0"))
        numerator = sum(
            ((r.sale_revenue_p2 / r.sale_qty_p2) * r.sale_qty_p1 for r in common),
            Decimal("0"),
        )

    if denominator == 0:
        return None
    return (numerator / denominator) * 100


def volume_index(rows: list[_ProductPeriodRow]) -> Decimal | None:
    """Sales-volume Laspeyres index — same family as price_index but with
    period-1 price held fixed and quantity varied (see "شاخص حجم فروش" in
    the doc). Always sale-side; there is no purchase-side volume index.
    Returns the raw ~100-based index; None when insufficient data.
    """
    common = _common_sale_rows(rows)
    if len(common) < MIN_COMMON_PRODUCTS:
        return None

    denominator = sum((r.sale_revenue_p1 for r in common), Decimal("0"))
    numerator = sum(
        ((r.sale_revenue_p1 / r.sale_qty_p1) * r.sale_qty_p2 for r in common),
        Decimal("0"),
    )
    if denominator == 0:
        return None
    return (numerator / denominator) * 100


def real_profit_index(cost_inflation_pct: Decimal | None, price_inflation_pct: Decimal | None) -> Decimal | None:
    """شاخص سود واقعی = تورم فروش − تورم خرید. Positive: sale prices are
    outrunning cost prices (margin improving); negative: costs are outrunning
    sale prices (margin eroding) even if nominal sales/profit look bigger.
    """
    if cost_inflation_pct is None or price_inflation_pct is None:
        return None
    return price_inflation_pct - cost_inflation_pct


def diagnose_status(
    price_inflation_pct: Decimal | None, volume_index_pct: Decimal | None
) -> dict | None:
    """Pure function (no query) — the 4-quadrant matrix from "تشخیص وضعیت
    اقتصادی فروشگاه" in the doc. Takes only the sign of the two already-
    computed indices and returns one of four pre-written labels + a summary
    sentence built from a fixed per-quadrant template with the actual
    numbers interpolated — never free-generated text. None (insufficient
    data) propagates from either input being None.
    """
    if price_inflation_pct is None or volume_index_pct is None:
        return None

    price_up = price_inflation_pct >= 0
    volume_up = volume_index_pct >= 0

    if price_up and volume_up:
        label, title = "healthy_growth", "رونق واقعی و سالم"
        clause = "قیمت‌ها بالاتر رفته و حجم واقعی فروش هم بیشتر شده — رشد سالم است."
    elif price_up and not volume_up:
        label, title = "stagflation", "رکود تورمی"
        clause = (
            "قیمت‌ها بالاتر رفته اما حجم واقعی فروش کم شده — درآمد اسمی می‌تواند "
            "رشد کرده به‌نظر برسد بدون اینکه فروش واقعی بیشتر شده باشد."
        )
    elif not price_up and volume_up:
        label, title = "successful_price_competition", "رقابت قیمتی موفق"
        clause = "قیمت‌ها پایین‌تر آمده ولی حجم فروش بیشتر شده — احتمالاً استراتژی قیمت‌گذاری رقابتی جواب داده است."
    else:
        label, title = "real_price_recession", "رکود واقعی/قیمتی"
        clause = "هم قیمت‌ها و هم حجم واقعی فروش کاهش یافته — نشانه‌ی رکود واقعی در تقاضاست."

    # Never interpolate a raw signed number here ("-10%") — always pick the
    # directional word and show the magnitude, matching how "already expired"
    # got a distinct label instead of looking like a generic red badge in the
    # near-expiry feature (see docs/inflation-rate-report.md's explicit
    # negative-inflation-isn't-an-error note).
    price_word = "تورم فروش" if price_inflation_pct >= 0 else "کاهش قیمت فروش"
    volume_word = "رشد" if volume_index_pct >= 0 else "رکود"
    summary_sentence = (
        f"این بازه: {price_word} {abs(price_inflation_pct):.0f}٪، {volume_word} حجم "
        f"{abs(volume_index_pct):.0f}٪ — وضعیت: {title}. {clause}"
    )

    return {"label": label, "title": title, "summary_sentence": summary_sentence}


def revenue_inflation_impact(
    database: Session,
    *,
    price_idx: Decimal | None,
    period1_start: date,
    period1_end: date,
    period2_start: date,
    period2_end: date,
) -> dict:
    """Nominal vs. inflation-adjusted ("real") revenue growth — see "گزارش
    تکمیلی: تاثیر تورم بر درآمد" in the doc. Nominal revenue is literally
    daily_sales_summary()'s own total (summed over the range), so this
    number always matches the dashboard for the same dates — no parallel
    revenue calculation.
    """
    nominal_p1 = sum(
        (row["total_sales"] for row in daily_sales_summary(database, from_date=period1_start, to_date=period1_end)),
        Decimal("0"),
    )
    nominal_p2 = sum(
        (row["total_sales"] for row in daily_sales_summary(database, from_date=period2_start, to_date=period2_end)),
        Decimal("0"),
    )

    nominal_growth_pct = ((nominal_p2 - nominal_p1) / nominal_p1 * 100) if nominal_p1 != 0 else None

    real_p2 = None
    real_growth_pct = None
    if price_idx is not None and price_idx != 0 and nominal_p1 != 0:
        real_p2 = nominal_p2 / (price_idx / 100)
        real_growth_pct = (real_p2 - nominal_p1) / nominal_p1 * 100
        # Money everywhere else in this app is Numeric(14, 2) — quantize
        # here too so the UI doesn't show a long division tail (e.g.
        # "...712.52193744...") that every other revenue figure never has.
        real_p2 = real_p2.quantize(Decimal("0.01"))

    return {
        "nominal_revenue_p1": nominal_p1,
        "nominal_revenue_p2": nominal_p2,
        "real_revenue_p2": real_p2,
        "nominal_growth_pct": nominal_growth_pct,
        "real_growth_pct": real_growth_pct,
    }


def category_inflation_breakdown(rows: list[_ProductPeriodRow]) -> list[dict]:
    """Same price/volume/diagnosis computation as the store-wide numbers,
    grouped by Category (see "شکست بر اساس دسته‌بندی کالا"). Uncategorized
    products are pooled under a single "سایر" bucket. The MIN_COMMON_PRODUCTS
    threshold is re-applied independently per category — a category can be
    insufficient even when the store-wide total is not.
    """
    groups: dict[int | None, list[_ProductPeriodRow]] = defaultdict(list)
    names: dict[int | None, str] = {}
    for row in rows:
        groups[row.category_id].append(row)
        names[row.category_id] = row.category_name or "سایر"

    result = []
    for category_id, group_rows in groups.items():
        cost_idx = price_index(group_rows, basis="cost")
        price_idx = price_index(group_rows, basis="price")
        volume_idx = volume_index(group_rows)

        cost_pct = (cost_idx - 100) if cost_idx is not None else None
        price_pct = (price_idx - 100) if price_idx is not None else None
        volume_pct = (volume_idx - 100) if volume_idx is not None else None

        result.append(
            {
                "category_id": category_id,
                "category_name": names[category_id],
                "cost_inflation_pct": cost_pct,
                "price_inflation_pct": price_pct,
                "volume_index_pct": volume_pct,
                "diagnosis": diagnose_status(price_pct, volume_pct),
                "insufficient_data": price_pct is None or volume_pct is None,
            }
        )

    result.sort(key=lambda item: (item["category_name"] == "سایر", item["category_name"]))
    return result


def biggest_price_increases(rows: list[_ProductPeriodRow], *, limit: int = 10) -> list[dict]:
    """Products with a sale in both periods, ranked by biggest %% price
    increase — the actionable twin of the headline price index (see
    "جزئیات UX" in the doc)."""
    result = []
    for r in _common_sale_rows(rows):
        price1 = r.sale_revenue_p1 / r.sale_qty_p1
        price2 = r.sale_revenue_p2 / r.sale_qty_p2
        if price1 == 0:
            continue
        result.append(
            {
                "product_id": r.product_id,
                "product_name": r.product_name,
                "price_period1": price1,
                "price_period2": price2,
                "pct_change": (price2 - price1) / price1 * 100,
            }
        )
    result.sort(key=lambda item: item["pct_change"], reverse=True)
    return result[:limit]


def biggest_volume_decliners(rows: list[_ProductPeriodRow], *, limit: int = 10) -> list[dict]:
    """Products with a sale in both periods, ranked by biggest %% drop in
    quantity sold — "کالاهای با بیشترین افت حجم فروش" in the doc."""
    result = []
    for r in _common_sale_rows(rows):
        if r.sale_qty_p1 == 0:
            continue
        result.append(
            {
                "product_id": r.product_id,
                "product_name": r.product_name,
                "quantity_period1": r.sale_qty_p1,
                "quantity_period2": r.sale_qty_p2,
                "pct_change": (r.sale_qty_p2 - r.sale_qty_p1) / r.sale_qty_p1 * 100,
            }
        )
    result.sort(key=lambda item: item["pct_change"])
    return result[:limit]


def inflation_rate(
    database: Session,
    *,
    period1_start: date,
    period1_end: date,
    period2_start: date,
    period2_end: date,
) -> dict:
    """Combined internal inflation-rate report — see
    docs/inflation-rate-report.md. One shared grouped dataset feeds every
    number below; nothing here duplicates a query.
    """
    rows = _inflation_raw_data(database, period1_start, period1_end, period2_start, period2_end)

    cost_idx = price_index(rows, basis="cost")
    price_idx = price_index(rows, basis="price")
    volume_idx = volume_index(rows)

    cost_inflation_pct = (cost_idx - 100) if cost_idx is not None else None
    price_inflation_pct = (price_idx - 100) if price_idx is not None else None
    volume_index_pct = (volume_idx - 100) if volume_idx is not None else None

    return {
        "cost_inflation_pct": cost_inflation_pct,
        "price_inflation_pct": price_inflation_pct,
        "volume_index_pct": volume_index_pct,
        "real_profit_index_pct": real_profit_index(cost_inflation_pct, price_inflation_pct),
        "insufficient_data": price_inflation_pct is None or volume_index_pct is None,
        "diagnosis": diagnose_status(price_inflation_pct, volume_index_pct),
        "revenue_impact": revenue_inflation_impact(
            database,
            price_idx=price_idx,
            period1_start=period1_start,
            period1_end=period1_end,
            period2_start=period2_start,
            period2_end=period2_end,
        ),
        "top_price_increases": biggest_price_increases(rows),
        "top_volume_decliners": biggest_volume_decliners(rows),
        "by_category": category_inflation_breakdown(rows),
    }


def net_profit(database: Session, period_start: date, period_end: date) -> dict:
    """سود خالص = سود ناخالص − هزینه‌های عملیاتی — see
    docs/expense-management.md. Gross profit reuses daily_sales_summary()'s
    own per-day "profit" column (the exact figure already shown on the
    dashboard/sales report), not a new parallel calculation.
    services/margin.py's calculate_margin_pct is a different concept (a
    single transaction's % margin, not an absolute period total) with no
    direct call site here — same conclusion reached for
    revenue_inflation_impact() above.
    """
    gross_profit = sum(
        (row["profit"] for row in daily_sales_summary(database, from_date=period_start, to_date=period_end)),
        Decimal("0"),
    )
    total_expenses = total_operating_expenses(database, period_start, period_end)
    return {
        "gross_profit": gross_profit,
        "total_operating_expenses": total_expenses,
        "net_profit": gross_profit - total_expenses,
    }
