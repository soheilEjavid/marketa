from datetime import datetime
from decimal import Decimal
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.entities import CheckStatus, DocumentStatus, PaymentMethod, PaymentStatus


class DualPriceConfig(BaseModel):
    """Configuration for entering dual-price mode on a single product."""
    suggested_new_sale_price: Decimal = Field(ge=0)


class PurchaseItemCreate(BaseModel):
    # Present + non-null only on an edit request, identifying an existing
    # PurchaseItem row to update. None means "new line" on an edit, and is
    # simply unused (always None) on a fresh purchase.
    id: int | None = None
    product_id: int
    quantity: Decimal = Field(gt=0)
    unit_cost: Decimal = Field(ge=0)
    selling_price: Decimal | None = Field(default=None, ge=0)
    expiry_date: date | None = None


class PurchasePaymentLineInput(BaseModel):
    """One payment line on a purchase — a purchase may have zero (fully on
    account), one, or several of these summing to at most the invoice total.
    """

    method: Literal["cash", "card", "check"]
    amount: Decimal = Field(gt=0)
    check_number: str | None = Field(default=None, max_length=60)
    check_bank_name: str | None = Field(default=None, max_length=120)
    check_due_date: date | None = None
    notes: str | None = Field(default=None, max_length=255)

    @field_validator("check_number", "check_bank_name", "notes", mode="before")
    @classmethod
    def normalize_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @model_validator(mode="after")
    def require_due_date_for_check(self) -> "PurchasePaymentLineInput":
        if self.method == "check" and self.check_due_date is None:
            raise ValueError("Check payment lines require a due date")
        return self


class PurchaseCreate(BaseModel):
    invoice_number: str | None = Field(default=None, max_length=50)
    supplier_id: int | None = None
    payment_lines: list[PurchasePaymentLineInput] = Field(default_factory=list)
    notes: str | None = None
    items: list[PurchaseItemCreate] = Field(min_length=1)
    confirm_dual_pricing: bool = False
    dual_pricing_new_sale_prices: dict[int, Decimal] | None = None


class PurchaseItemRead(BaseModel):
    id: int
    product_id: int
    quantity: Decimal
    unit_cost: Decimal
    selling_price: Decimal | None
    expiry_date: date | None
    line_total: Decimal

    model_config = ConfigDict(from_attributes=True)


class PurchaseEditRequest(BaseModel):
    """Edit an existing purchase's line items.

    Deliberately narrow scope: supplier and invoice number are NOT editable
    here. Dual-pricing is never (re-)triggered by an edit — if any line's
    product currently has an active dual-price state, the edit is blocked
    entirely by the service layer rather than guessing at the correct
    cascade (see the invoice-editing task write-up).
    """

    items: list[PurchaseItemCreate] = Field(min_length=1)
    reason: str | None = Field(default=None, max_length=500)

    @field_validator("reason", mode="before")
    @classmethod
    def normalize_reason(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class PurchasePaymentLineRead(BaseModel):
    id: int
    method: PaymentMethod
    amount: Decimal
    check_number: str | None
    check_bank_name: str | None
    check_due_date: date | None
    check_status: CheckStatus | None
    notes: str | None
    paid_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PurchaseRead(BaseModel):
    id: int
    invoice_number: str
    supplier_id: int | None
    total: Decimal
    paid_amount: Decimal
    remaining_amount: Decimal
    payment_status: PaymentStatus
    status: DocumentStatus
    notes: str | None
    created_at: datetime
    items: list[PurchaseItemRead]
    payment_lines: list[PurchasePaymentLineRead] = []

    model_config = ConfigDict(from_attributes=True)
