from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel

from app.models.entities import CheckStatus


class CheckRead(BaseModel):
    id: int
    supplier_id: int | None
    supplier_name: str | None
    purchase_id: int | None
    purchase_invoice_number: str | None
    amount: Decimal
    check_number: str | None
    check_bank_name: str | None
    check_due_date: date | None
    check_status: CheckStatus
    notes: str | None
    paid_at: datetime


class CheckStatusUpdate(BaseModel):
    status: CheckStatus


class CheckSummary(BaseModel):
    due_this_week: Decimal
    due_this_month: Decimal
