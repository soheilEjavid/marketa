from datetime import datetime
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from app.models.entities import PaymentMethod, PaymentStatus

class PaymentCreate(BaseModel):
    amount: Decimal = Field(gt=0)
    document_id: int | None = None
    method: PaymentMethod = PaymentMethod.CARD
    reference: str | None = Field(default=None, max_length=120)
    notes: str | None = None

class PaymentRead(BaseModel):
    id: int
    amount: Decimal
    method: PaymentMethod
    reference: str | None
    notes: str | None
    paid_at: datetime
    model_config = ConfigDict(from_attributes=True)

class LedgerEntry(BaseModel):
    id: str
    occurred_at: datetime
    entry_type: Literal["sale", "purchase", "payment"]
    reference: str
    description: str
    debit: Decimal
    credit: Decimal
    running_balance: Decimal
    payment_status: PaymentStatus | None = None

class CustomerLedger(BaseModel):
    customer_id: int
    customer_name: str
    balance: Decimal
    entries: list[LedgerEntry]

class SupplierLedger(BaseModel):
    supplier_id: int
    supplier_name: str
    balance: Decimal
    entries: list[LedgerEntry]
