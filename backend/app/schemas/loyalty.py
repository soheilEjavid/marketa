from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class LoyaltyBalanceRead(BaseModel):
    customer_id: int
    points_balance: int
    points_value_toman: Decimal
    # Only meaningful when `sale_total` was passed to the endpoint —
    # otherwise mirrors points_balance uncapped.
    max_redeemable_points: int
    # Whether the customer has crossed the manager-configurable
    # auto-enrollment threshold (or always True when no threshold is set).
    is_member: bool
    # "bronze" (base tier) / "silver" / "gold" — see services/loyalty.py::customer_tier().
    tier: str


class LoyaltyAdjustRequest(BaseModel):
    delta: int = Field(description="Positive to add points, negative to remove")
    reason: str = Field(min_length=3, max_length=500)

    @field_validator("reason")
    @classmethod
    def strip_reason(cls, value: str) -> str:
        stripped = value.strip()
        if len(stripped) < 3:
            raise ValueError("Reason must be at least 3 characters")
        return stripped


class LoyaltyTransactionRead(BaseModel):
    id: int
    points: int
    transaction_type: str
    sale_id: int | None
    expires_at: datetime | None
    expired: bool
    reason: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LoyaltySettingsRead(BaseModel):
    min_invoice_total_for_membership: Decimal | None
    min_invoice_profit_for_membership: Decimal | None
    # Null disables that tier (or, if both are null, tiers entirely).
    tier_silver_min_spend: Decimal | None
    tier_gold_min_spend: Decimal | None
    # Null means tier spend is measured all-time/lifetime; otherwise only
    # the trailing tier_window_days days count toward a customer's tier.
    tier_window_days: int | None
    # Null disables that tier's earn-rate bonus.
    tier_silver_earn_bonus: Decimal | None
    tier_gold_earn_bonus: Decimal | None
    # Null/0 disables automated churn-recovery coupon issuance.
    churn_recovery_coupon_points: int | None

    model_config = ConfigDict(from_attributes=True)


class LoyaltySettingsUpdate(BaseModel):
    # Explicit null clears the threshold (feature disabled for that axis) —
    # every customer becomes a member immediately again, matching the
    # program's original design.
    min_invoice_total_for_membership: Decimal | None = Field(default=None, ge=0)
    min_invoice_profit_for_membership: Decimal | None = Field(default=None, ge=0)
    tier_silver_min_spend: Decimal | None = Field(default=None, ge=0)
    tier_gold_min_spend: Decimal | None = Field(default=None, ge=0)
    tier_window_days: int | None = Field(default=None, ge=1)
    tier_silver_earn_bonus: Decimal | None = Field(default=None, ge=0)
    tier_gold_earn_bonus: Decimal | None = Field(default=None, ge=0)
    churn_recovery_coupon_points: int | None = Field(default=None, ge=0)


class LoyaltyRewardSuggestionRow(BaseModel):
    product_id: int
    product_name: str
    sale_price: Decimal
    points_required: int
    affordable: bool
    reason: Literal["near_expiry", "dead_stock"]
    days_until_expiry: int | None


class LoyaltyRewardCatalogRow(BaseModel):
    product_id: int
    product_name: str
    sale_price: Decimal
    points_required: int
    is_suggested: bool
    reason: Literal["near_expiry", "dead_stock"] | None


class ChurnCouponIssueResult(BaseModel):
    customer_id: int
    customer_name: str
    points: int
