from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.models.entities import Customer, CustomerPayment, DocumentStatus, Product, Sale, SaleItem, Supplier

def get_summary(database: Session) -> dict:
    today = datetime.now(UTC).date()
    today_start = datetime.combine(today, datetime.min.time(), tzinfo=UTC)
    today_sales, today_transactions = database.execute(select(func.coalesce(func.sum(Sale.total), 0), func.count(Sale.id)).where(Sale.status == DocumentStatus.COMPLETED, Sale.created_at >= today_start)).one()
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
    trend = []
    profit_trend = []
    for days_ago in range(6, -1, -1):
        day = today - timedelta(days=days_ago)
        start = datetime.combine(day, datetime.min.time(), tzinfo=UTC)
        end = start + timedelta(days=1)
        amount = database.scalar(select(func.coalesce(func.sum(Sale.total), 0)).where(Sale.status == DocumentStatus.COMPLETED, Sale.created_at >= start, Sale.created_at < end)) or Decimal('0')
        trend.append({"date": day, "sales": amount})
        # profit = sum of (unit_price - cost_price) * quantity for completed sales that day
        profit_row = database.execute(
            select(func.coalesce(func.sum((SaleItem.unit_price - SaleItem.cost_price) * SaleItem.quantity), 0))
            .join(Sale)
            .where(
                Sale.status == DocumentStatus.COMPLETED,
                Sale.created_at >= start,
                Sale.created_at < end,
            )
        ).scalar() or Decimal('0')
        profit_trend.append({"date": day, "profit": profit_row})
    return {"today_sales": today_sales, "today_transactions": today_transactions, "active_products": active_products, "low_stock_products": low_stock_products, "total_receivables": receivables, "total_payables": payables, "top_debtors": [{"customer_id": row.id, "customer_name": row.full_name, "phone": row.phone, "balance": row.balance} for row in debtors], "recent_customer_activity": activities[:8], "sales_trend": trend, "profit_trend": profit_trend}
