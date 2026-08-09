from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.core.store_time import business_day, business_day_bounds, business_day_now
from app.models.entities import Customer, CustomerPayment, DocumentStatus, Product, Sale, SaleItem, Supplier

def get_summary(database: Session) -> dict:
    today = business_day_now()
    # Half-open [start, end) over the raw column, so "today's sales" runs on
    # the index instead of computing a trading day for every row in the
    # table. business_day_bounds() puts those two instants where the shop's
    # own clock says the day begins and ends.
    today_start, today_end = business_day_bounds(today)
    today_sales, today_transactions = database.execute(select(func.coalesce(func.sum(Sale.total), 0), func.count(Sale.id)).where(Sale.status == DocumentStatus.COMPLETED, Sale.created_at >= today_start, Sale.created_at < today_end)).one()
    active_products = database.scalar(select(func.count(Product.id)).where(Product.is_active.is_(True))) or 0
    low_stock_products = database.scalar(select(func.count(Product.id)).where(Product.is_active.is_(True), Product.stock_quantity <= Product.low_stock_threshold)) or 0
    receivables = database.scalar(select(func.coalesce(func.sum(Customer.balance), 0))) or Decimal('0')
    payables = database.scalar(select(func.coalesce(func.sum(Supplier.balance), 0))) or Decimal('0')
    debtors = database.execute(select(Customer.id, Customer.full_name, Customer.phone, Customer.balance).where(Customer.balance > 0).order_by(Customer.balance.desc()).limit(5)).all()
    activities = []
    sales = database.execute(select(Sale, Customer.full_name).join(Customer).order_by(Sale.created_at.desc()).limit(8)).all()
    payments = database.execute(select(CustomerPayment, Customer.full_name).join(Customer).order_by(CustomerPayment.paid_at.desc()).limit(8)).all()
    for sale, name in sales:
        activities.append({"customer_id": sale.customer_id, "customer_name": name, "entry_type": "sale", "reference": sale.invoice_number, "amount": sale.total, "occurred_at": sale.created_at, "payment_status": sale.payment_status})
    for payment, name in payments:
        activities.append({"customer_id": payment.customer_id, "customer_name": name, "entry_type": "payment", "reference": payment.reference or f"REC-{payment.id:05d}", "amount": payment.amount, "occurred_at": payment.paid_at, "payment_status": None})
    activities.sort(key=lambda item: item["occurred_at"], reverse=True)
    # Seven days of sales and profit, in two grouped queries rather than the
    # fourteen this used to run one day at a time — that loop made
    # /dashboard/summary the slowest endpoint in the app.
    window_start, _ = business_day_bounds(today - timedelta(days=6))
    _, window_end = business_day_bounds(today)

    sales_by_day = {
        row[0]: row[1]
        for row in database.execute(
            select(business_day(Sale.created_at), func.coalesce(func.sum(Sale.total), 0))
            .where(
                Sale.status == DocumentStatus.COMPLETED,
                Sale.created_at >= window_start,
                Sale.created_at < window_end,
            )
            .group_by(business_day(Sale.created_at))
        ).all()
    }

    # Same definition of profit as services/reports.py::daily_sales_summary,
    # deliberately: this used to run its own parallel formula,
    # (unit_price - cost_price) * quantity, which ignored BOTH the per-item
    # discount (line_total already nets that off) and the invoice-level one,
    # so the dashboard chart and the reports page disagreed about the same
    # day. Profit has to be measured against the revenue actually taken.
    item_profit_by_day = {
        row[0]: row[1]
        for row in database.execute(
            select(
                business_day(Sale.created_at),
                func.coalesce(func.sum(SaleItem.line_total - (SaleItem.cost_price * SaleItem.quantity)), 0),
            )
            .join(Sale, Sale.id == SaleItem.sale_id)
            .where(
                Sale.status == DocumentStatus.COMPLETED,
                Sale.created_at >= window_start,
                Sale.created_at < window_end,
            )
            .group_by(business_day(Sale.created_at))
        ).all()
    }
    invoice_discount_by_day = {
        row[0]: row[1]
        for row in database.execute(
            select(business_day(Sale.created_at), func.coalesce(func.sum(Sale.discount), 0))
            .where(
                Sale.status == DocumentStatus.COMPLETED,
                Sale.created_at >= window_start,
                Sale.created_at < window_end,
            )
            .group_by(business_day(Sale.created_at))
        ).all()
    }

    trend = []
    profit_trend = []
    for days_ago in range(6, -1, -1):
        day = today - timedelta(days=days_ago)
        # business_day() is typed as a Date, so these come back as real date
        # objects — the old func.date() handed back ISO strings and this
        # looked them up with day.isoformat().
        trend.append({"date": day, "sales": sales_by_day.get(day, Decimal('0'))})
        profit_trend.append({
            "date": day,
            "profit": Decimal(str(item_profit_by_day.get(day, 0)))
            - Decimal(str(invoice_discount_by_day.get(day, 0))),
        })
    return {"today_sales": today_sales, "today_transactions": today_transactions, "active_products": active_products, "low_stock_products": low_stock_products, "total_receivables": receivables, "total_payables": payables, "top_debtors": [{"customer_id": row.id, "customer_name": row.full_name, "phone": row.phone, "balance": row.balance} for row in debtors], "recent_customer_activity": activities[:8], "sales_trend": trend, "profit_trend": profit_trend}
