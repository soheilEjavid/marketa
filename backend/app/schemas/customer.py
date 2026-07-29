from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator


def normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


class CustomerBase(BaseModel):
    full_name: str = Field(min_length=2, max_length=160)
    phone: str | None = Field(default=None, max_length=40)
    national_id: str | None = Field(default=None, min_length=8, max_length=20)
    address: str | None = None
    notes: str | None = None
    credit_limit: Decimal = Field(default=Decimal("0"), ge=0)
    is_active: bool = True
    # Optional — many customers won't share it. Used for the birthday report.
    birth_date: date | None = None

    @field_validator(
        "full_name", "phone", "national_id", "address", "notes", mode="before"
    )
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        return normalize_optional_text(value)


class CustomerCreate(CustomerBase):
    # Lets the post-checkout quick-add flow (a large, no-customer sale that
    # crossed the membership threshold) enroll the new customer as a
    # loyalty member immediately — see services/loyalty.py's membership
    # design note. Never retroactively applies to the sale that prompted
    # it; only affects purchases from here on.
    loyalty_member: bool = False


class CustomerUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=160)
    phone: str | None = Field(default=None, max_length=40)
    national_id: str | None = Field(default=None, min_length=8, max_length=20)
    address: str | None = None
    notes: str | None = None
    credit_limit: Decimal | None = Field(default=None, ge=0)
    is_active: bool | None = None
    birth_date: date | None = None

    @field_validator(
        "full_name", "phone", "national_id", "address", "notes", mode="before"
    )
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        return normalize_optional_text(value)


class CustomerRead(CustomerBase):
    id: int
    balance: Decimal
    loyalty_points_balance: int
    loyalty_member: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
