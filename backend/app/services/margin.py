"""Backend port of frontend/src/lib/margin.ts — the single source of truth
for margin-on-sales math shared by the loyalty points system (and any
future backend code that needs the same figure). Keep these two files'
formulas identical; if one changes, change the other.
"""

from decimal import Decimal
from enum import StrEnum


class MarginStatus(StrEnum):
    NEGATIVE = "negative"
    LOW = "low"
    HEALTHY = "healthy"


def calculate_margin_pct(sale_price: Decimal, cost_price: Decimal) -> Decimal | None:
    """Margin-on-sales (not markup-on-cost): (salePrice - costPrice) / salePrice * 100.
    None when sale_price is not positive — margin is undefined in that case.
    """
    if sale_price <= 0:
        return None
    return ((sale_price - cost_price) / sale_price) * 100


def get_margin_status(margin_pct: Decimal) -> MarginStatus:
    if margin_pct < 0:
        return MarginStatus.NEGATIVE
    if margin_pct < 15:
        return MarginStatus.LOW
    return MarginStatus.HEALTHY
