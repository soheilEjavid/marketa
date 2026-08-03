from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel


class DailySalesSummary(BaseModel):
    date: date
    total_sales: Decimal
    transaction_count: int
    average_ticket: Decimal
    profit: Decimal


class ProductSalesSummary(BaseModel):
    product_id: int
    product_name: str
    total_quantity: Decimal
    total_revenue: Decimal
    total_profit: Decimal


class LowStockReport(BaseModel):
    product_id: int
    product_name: str
    stock_quantity: Decimal
    low_stock_threshold: Decimal


class InventorySummary(BaseModel):
    product_id: int
    product_name: str
    stock_quantity: Decimal
    purchase_price: Decimal
    sale_price: Decimal
    total_stock_value: Decimal
    potential_profit: Decimal | None
    estimated_value: Decimal


class DeadStockRow(BaseModel):
    product_id: int
    product_name: str
    category_name: str | None
    stock_quantity: Decimal
    days_since_last_sale: int | None
    value_tied_up: Decimal


class NearExpiryRow(BaseModel):
    product_id: int
    product_name: str
    stock_quantity: Decimal
    expiration_date: date
    days_until_expiry: int
    status: Literal["expired", "red", "orange"]


class CashierPerformanceRow(BaseModel):
    cashier_id: int
    cashier_name: str
    invoice_count: int
    total_sales: Decimal
    average_ticket: Decimal
    total_discount: Decimal
    payment_method_breakdown: dict[str, Decimal]
    edited_count: int
    held_count: int
    discarded_count: int


class CustomerBalanceSummary(BaseModel):
    customer_id: int
    customer_name: str
    balance: Decimal
    credit_limit: Decimal


class OutstandingConsignmentRow(BaseModel):
    purchase_item_id: int
    purchase_id: int
    invoice_number: str
    supplier_id: int | None
    supplier_name: str | None
    product_id: int
    product_name: str
    quantity: Decimal
    value: Decimal
    received_at: datetime


class SupplierBalanceSummary(BaseModel):
    supplier_id: int
    supplier_name: str
    balance: Decimal
    credit_limit: Decimal


class PaymentMethodBreakdown(BaseModel):
    payment_method: str
    total: Decimal
    transaction_count: int


class LoyaltyLiabilityRow(BaseModel):
    customer_id: int
    customer_name: str
    points_balance: int
    points_value_toman: Decimal


class BirthdayCustomerRow(BaseModel):
    customer_id: int
    customer_name: str
    phone: str | None
    birth_date: date
    days_until_birthday: int


class ChurnRiskCustomerRow(BaseModel):
    customer_id: int
    customer_name: str
    phone: str | None
    purchase_count_recent: int
    last_purchase_at: datetime
    days_since_last_purchase: int


class CustomerTierRow(BaseModel):
    customer_id: int
    customer_name: str
    lifetime_spend: Decimal
    tier: str


class LoyaltyRedemptionRow(BaseModel):
    payment_id: int
    customer_id: int
    customer_name: str
    sale_id: int | None
    invoice_number: str | None
    discount_value: Decimal
    points_used: int
    product_names: list[str]
    paid_at: datetime
