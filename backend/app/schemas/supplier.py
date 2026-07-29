from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.customer import normalize_optional_text


class SupplierBase(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    contact_person: str | None = Field(default=None, max_length=120)
    phone: str | None = Field(default=None, max_length=40)
    address: str | None = None
    notes: str | None = None
    credit_limit: Decimal = Field(default=Decimal("0"), ge=0)
    is_active: bool = True

    @field_validator(
        "name", "contact_person", "phone", "address", "notes", mode="before"
    )
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        return normalize_optional_text(value)


class SupplierCreate(SupplierBase):
    pass


class SupplierUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    contact_person: str | None = Field(default=None, max_length=120)
    phone: str | None = Field(default=None, max_length=40)
    address: str | None = None
    notes: str | None = None
    credit_limit: Decimal = Field(default=Decimal("0"), ge=0)
    is_active: bool | None = None

    @field_validator(
        "name", "contact_person", "phone", "address", "notes", mode="before"
    )
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        return normalize_optional_text(value)


class SupplierRead(SupplierBase):
    id: int
    balance: Decimal
    last_purchase_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
