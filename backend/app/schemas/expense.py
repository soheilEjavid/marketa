from datetime import date as _date
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.entities import ExpensePaymentMethod


def _strip(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


class ExpenseCreate(BaseModel):
    category: str = Field(min_length=1, max_length=100)
    amount: Decimal = Field(gt=0)
    date: _date
    description: str | None = None
    is_recurring: bool = False
    payment_method: ExpensePaymentMethod
    receipt_image_url: str | None = None

    @field_validator("category", mode="before")
    @classmethod
    def strip_category(cls, value: str) -> str:
        return value.strip() if isinstance(value, str) else value

    @field_validator("description", "receipt_image_url", mode="before")
    @classmethod
    def strip_optional(cls, value: str | None) -> str | None:
        return _strip(value)


class ExpenseUpdate(BaseModel):
    category: str | None = Field(default=None, min_length=1, max_length=100)
    amount: Decimal | None = Field(default=None, gt=0)
    date: _date | None = None
    description: str | None = None
    is_recurring: bool | None = None
    payment_method: ExpensePaymentMethod | None = None
    receipt_image_url: str | None = None

    @field_validator("category", mode="before")
    @classmethod
    def strip_category(cls, value: str | None) -> str | None:
        return value.strip() if isinstance(value, str) else value

    @field_validator("description", "receipt_image_url", mode="before")
    @classmethod
    def strip_optional(cls, value: str | None) -> str | None:
        return _strip(value)


class ExpenseRead(BaseModel):
    id: int
    category: str
    amount: Decimal
    date: _date
    description: str | None
    is_recurring: bool
    payment_method: ExpensePaymentMethod
    receipt_image_url: str | None
    created_by_user_id: int | None

    model_config = ConfigDict(from_attributes=True)


class SalaryAdvanceCreate(BaseModel):
    employee_id: int
    amount: Decimal = Field(gt=0)
    date: _date
    notes: str | None = None

    @field_validator("notes", mode="before")
    @classmethod
    def strip_notes(cls, value: str | None) -> str | None:
        return _strip(value)


class SalaryAdvanceRead(BaseModel):
    id: int
    employee_id: int
    employee_name: str
    amount: Decimal
    date: _date
    notes: str | None
    settled_in_payment_id: int | None

    model_config = ConfigDict(from_attributes=True)


class SalaryPaymentCreate(BaseModel):
    employee_id: int
    # Jalali year/month (e.g. 1405, 5) — a plain identifying label for the
    # payroll cycle, not a Gregorian calendar moment, matching how an
    # Iranian shop actually names a payroll cycle ("حقوق مرداد ۱۴۰۵").
    # Every other date/datetime column in this backend stays Gregorian;
    # this pair is the one deliberate exception, since it never needs date
    # arithmetic — only identity + the uniqueness constraint.
    period_year: int = Field(ge=1300, le=1500)
    period_month: int = Field(ge=1, le=12)
    base_amount: Decimal = Field(ge=0)
    bonus_amount: Decimal = Field(default=Decimal("0"), ge=0)
    # Manual deductions only (insurance, unpaid leave, etc.) — unsettled
    # SalaryAdvance rows for this employee are folded in automatically by
    # services/expenses.py::create_salary_payment, not typed here.
    other_deductions_amount: Decimal = Field(default=Decimal("0"), ge=0)
    payment_method: ExpensePaymentMethod
    notes: str | None = None

    @field_validator("notes", mode="before")
    @classmethod
    def strip_notes(cls, value: str | None) -> str | None:
        return _strip(value)


class SalaryPaymentUpdate(BaseModel):
    base_amount: Decimal | None = Field(default=None, ge=0)
    bonus_amount: Decimal | None = Field(default=None, ge=0)
    other_deductions_amount: Decimal | None = Field(default=None, ge=0)
    payment_method: ExpensePaymentMethod | None = None
    notes: str | None = None

    @field_validator("notes", mode="before")
    @classmethod
    def strip_notes(cls, value: str | None) -> str | None:
        return _strip(value)


class SalaryPaymentRead(BaseModel):
    id: int
    employee_id: int
    employee_name: str
    period_year: int
    period_month: int
    base_amount: Decimal
    bonus_amount: Decimal
    deductions_amount: Decimal
    net_amount: Decimal
    payment_method: ExpensePaymentMethod
    paid_at: datetime
    notes: str | None
    created_by_user_id: int | None

    model_config = ConfigDict(from_attributes=True)


class NetProfitReport(BaseModel):
    gross_profit: Decimal
    total_operating_expenses: Decimal
    net_profit: Decimal
