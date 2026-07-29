from datetime import date, datetime
from decimal import Decimal
from pydantic import BaseModel
from app.models.entities import PaymentStatus

class DashboardDebtor(BaseModel):
    customer_id: int
    customer_name: str
    phone: str | None
    balance: Decimal

class DashboardActivity(BaseModel):
    customer_id: int
    customer_name: str
    entry_type: str
    reference: str
    amount: Decimal
    occurred_at: datetime
    payment_status: PaymentStatus | None = None

class DashboardTrendPoint(BaseModel):
    date: date
    sales: Decimal

class ProfitTrendPoint(BaseModel):
    date: date
    profit: Decimal

class DashboardSummary(BaseModel):
    today_sales: Decimal
    today_transactions: int
    active_products: int
    low_stock_products: int
    total_receivables: Decimal
    total_payables: Decimal
    top_debtors: list[DashboardDebtor]
    recent_customer_activity: list[DashboardActivity]
    sales_trend: list[DashboardTrendPoint]
    profit_trend: list[ProfitTrendPoint]
