from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.entities import CheckStatus, DocumentStatus, PaymentStatus, PaymentMethod


class SaleItemCreate(BaseModel):
    # Present + non-null only on an edit request, identifying an existing
    # SaleItem row to update. None means "new line" on an edit, and is
    # simply unused (always None) on a fresh sale.
    id: int | None = None
    product_id: int
    quantity: Decimal = Field(gt=0)
    unit_price: Decimal | None = Field(default=None, ge=0)
    discount: Decimal = Field(default=Decimal("0"), ge=0)
    price_tier: Literal["old", "new"] | None = None


class SalePaymentLineInput(BaseModel):
    """One payment line on a sale — mirrors PurchasePaymentLineInput. A sale
    may have zero (fully on account), one, or several of these summing to at
    most the post-redemption remaining amount.
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
    def require_due_date_for_check(self) -> "SalePaymentLineInput":
        if self.method == "check" and self.check_due_date is None:
            raise ValueError("Check payment lines require a due date")
        return self


class SaleCreate(BaseModel):
    invoice_number: str | None = Field(default=None, max_length=50)
    customer_id: int | None = None
    discount: Decimal = Field(default=Decimal("0"), ge=0)
    # Legacy single-method fields — still fully supported. Read only when
    # payment_lines is empty (see services/sales.py::process_sale).
    paid_amount: Decimal | None = Field(default=None, ge=0)
    payment_method: PaymentMethod = PaymentMethod.CASH
    # New split-payment fields. A non-empty list takes over entirely from
    # payment_method/paid_amount above — see the audit note in
    # services/sales.py for why both mechanisms coexist.
    payment_lines: list[SalePaymentLineInput] = Field(default_factory=list)
    notes: str | None = None
    items: list[SaleItemCreate] = Field(min_length=1)
    # کالای وفاداری: how many loyalty points the customer wants to redeem
    # against this invoice — see services/loyalty.py for the cap/validation.
    redeem_points: int = Field(default=0, ge=0)
    # Requests proceeding past a customer's credit_limit. Only actually
    # honored if the authenticated caller is admin/manager — the route
    # re-derives that from the JWT role, never trusts this flag alone (see
    # services/sales.py::CreditLimitExceededError).
    allow_credit_override: bool = False


class SaleItemRead(BaseModel):
    id: int
    product_id: int
    quantity: Decimal
    unit_price: Decimal
    cost_price: Decimal
    discount: Decimal
    line_total: Decimal
    price_tier: str | None = None

    model_config = ConfigDict(from_attributes=True)


class SaleEditRequest(BaseModel):
    """Edit an existing sale's line items and/or invoice discount.

    Deliberately narrow scope: customer, payment method, and invoice number
    are NOT editable here (out of scope — see the invoice-editing task).
    Only quantity/price/discount per line, and the whole-invoice discount.
    """

    discount: Decimal = Field(default=Decimal("0"), ge=0)
    items: list[SaleItemCreate] = Field(min_length=1)
    reason: str | None = Field(default=None, max_length=500)

    @field_validator("reason", mode="before")
    @classmethod
    def normalize_reason(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class SalePaymentLineRead(BaseModel):
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


class SaleRead(BaseModel):
    id: int
    invoice_number: str
    customer_id: int | None
    subtotal: Decimal
    discount: Decimal
    total: Decimal
    paid_amount: Decimal
    remaining_amount: Decimal
    payment_status: PaymentStatus
    payment_method: PaymentMethod
    status: DocumentStatus
    notes: str | None
    created_at: datetime
    items: list[SaleItemRead]
    payment_lines: list[SalePaymentLineRead] = []
    shift_id: int | None = None
    # Transient (never persisted) — True only on the POST /sales response
    # for the exact sale whose payment crossed the loyalty membership
    # threshold (see services/sales.py::process_sale). Always False from
    # every other endpoint that returns a Sale (list/get/hold/edit/etc).
    loyalty_membership_just_earned: bool = False

    model_config = ConfigDict(from_attributes=True)
