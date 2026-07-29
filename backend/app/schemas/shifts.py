from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.entities import ShiftStatus


class ShiftOpenRequest(BaseModel):
    cashier_id: int
    opening_cash: Decimal = Field(ge=0)


class ShiftCloseRequest(BaseModel):
    closing_cash: Decimal = Field(ge=0)
    notes: str | None = Field(default=None, max_length=500)


class ShiftRead(BaseModel):
    id: int
    cashier_id: int
    cashier_name: str
    status: ShiftStatus
    opening_cash: Decimal
    closing_cash: Decimal | None
    expected_cash: Decimal | None
    difference: Decimal | None
    opened_at: datetime
    closed_at: datetime | None
    notes: str | None
