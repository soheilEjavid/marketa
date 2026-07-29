from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.orm import selectinload

from app.models.entities import (
    AuditLog, CashierShift, Category, Customer, CustomerPayment, DocumentStatus, PaymentMethod,
    Product, Purchase, PurchaseItem, Sale, SaleItem, Supplier, User,
)


def daily_sales_summary(
    database: Session,
    *,
    from_date: date | None = None,
    to_date: date | None = None,
) -> list[dict]:
    today = datetime.now(UTC).date()
    from_date = from_date or today - timedelta(days=30)
    to_date = to_date or today
    sale_rows = (
        select(
            Sale.id.label("sale_id"),
            func.date(Sale.created_at).label("sale_date"),
            Sale.total,
        )
        .where(
            Sale.status == DocumentStatus.COMPLETED,
            func.date(Sale.created_at) >= from_date,
            func.date(Sale.created_at) <= to_date,
        )
        .subquery()
    )

    sales_summary = (
        select(
            sale_rows.c.sale_date.label("sale_date"),
            func.coalesce(func.sum(sale_rows.c.total), 0).label("total_sales"),
            func.count(sale_rows.c.sale_id).label("transaction_count"),
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
            func.coalesce(profit_summary.c.profit, Decimal("0")).label("profit"),
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
    today = datetime.now(UTC).date()
    from_date = from_date or today - timedelta(days=30)
    to_date = to_date or today
    rows = database.execute(
        select(
            Sale.payment_method,
            func.coalesce(func.sum(Sale.total), 0),
            func.count(Sale.id),
        )
        .where(
            Sale.status == DocumentStatus.COMPLETED,
            func.date(Sale.created_at) >= from_date,
            func.date(Sale.created_at) <= to_date,
        )
        .group_by(Sale.payment_method)
        .order_by(func.sum(Sale.total).desc())
    ).all()
    return [
        {
            "payment_method": row[0],
            "total": row[1],
            "transaction_count": row[2],
        }
        for row in rows
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
    today = datetime.now(UTC).date()
    cutoff = today - timedelta(days=lookback_days)

    last_sale = (
        select(
            SaleItem.product_id.label("product_id"),
            func.max(func.date(Sale.created_at)).label("last_sale_date"),
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
    for product_id, product_name, category_name, stock_quantity, purchase_price, last_sale_date_str in rows:
        if last_sale_date_str is not None:
            last_sale_date = date.fromisoformat(last_sale_date_str)
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


def cashier_performance(
    database: Session,
    *,
    from_date: date | None = None,
    to_date: date | None = None,
) -> list[dict]:
    """Per-cashier aggregates for completed sales attributed via
    Sale.shift_id -> CashierShift.cashier_id — deliberately NOT via
    AuditLog.user_id, which is always the DEV_DISABLE_AUTH bypass user
    regardless of which cashier is actually working the register. "Refund
    amount" from the original spec is omitted entirely: this codebase has
    no sales-refund/return concept at all, and fabricating a zero would
    violate the "no calculated fake values" requirement.
    """
    today = datetime.now(UTC).date()
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
            func.date(Sale.created_at) >= from_date,
            func.date(Sale.created_at) <= to_date,
        )
        .group_by(CashierShift.cashier_id, User.full_name)
    ).all()

    method_rows = database.execute(
        select(
            CashierShift.cashier_id,
            Sale.payment_method,
            func.coalesce(func.sum(Sale.total), 0),
        )
        .select_from(Sale)
        .join(CashierShift, Sale.shift_id == CashierShift.id)
        .where(
            Sale.status == DocumentStatus.COMPLETED,
            func.date(Sale.created_at) >= from_date,
            func.date(Sale.created_at) <= to_date,
        )
        .group_by(CashierShift.cashier_id, Sale.payment_method)
    ).all()
    breakdown_by_cashier: dict[int, dict[str, Decimal]] = defaultdict(dict)
    for cashier_id, method, total in method_rows:
        breakdown_by_cashier[cashier_id][str(method.value if hasattr(method, "value") else method)] = total

    # Held/edited/discarded counts: joined through the sale each audit entry
    # refers to, then through that sale's shift — NOT through
    # AuditLog.user_id, which the DEV_DISABLE_AUTH bypass makes meaningless.
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
            func.date(AuditLog.occurred_at) >= from_date,
            func.date(AuditLog.occurred_at) <= to_date,
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


def outstanding_consignment(database: Session) -> list[dict]:
    """All کالای امانی purchase-item lines not yet settled — see
    services/purchases.settle_consignment_item for how settlement works.
    """
    items = database.scalars(
        select(PurchaseItem)
        .join(Purchase, PurchaseItem.purchase_id == Purchase.id)
        .where(
            PurchaseItem.is_consignment.is_(True),
            PurchaseItem.consignment_settled_at.is_(None),
        )
        .options(selectinload(PurchaseItem.purchase).selectinload(Purchase.supplier), selectinload(PurchaseItem.product))
        .order_by(Purchase.created_at.desc())
    ).all()
    return [
        {
            "purchase_item_id": item.id,
            "purchase_id": item.purchase_id,
            "invoice_number": item.purchase.invoice_number,
            "supplier_id": item.purchase.supplier_id,
            "supplier_name": item.purchase.supplier.name if item.purchase.supplier else None,
            "product_id": item.product_id,
            "product_name": item.product.name,
            "quantity": item.quantity,
            "value": item.line_total,
            "received_at": item.purchase.created_at,
        }
        for item in items
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
        query = query.where(CustomerPayment.paid_at >= datetime.combine(from_date, datetime.min.time(), tzinfo=UTC))
    if to_date:
        query = query.where(CustomerPayment.paid_at <= datetime.combine(to_date, datetime.max.time(), tzinfo=UTC))

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
    today = datetime.now(UTC).date()
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
