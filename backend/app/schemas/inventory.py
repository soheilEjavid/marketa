from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.models.entities import InventoryTransactionType


class InventoryTransactionRead(BaseModel):
    id: int
    product_id: int
    product_name: str
    quantity_change: Decimal
    transaction_type: InventoryTransactionType
    related_id: int | None
    timestamp: datetime

    model_config = ConfigDict(from_attributes=True)
