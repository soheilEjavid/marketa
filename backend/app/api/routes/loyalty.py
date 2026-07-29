from fastapi import APIRouter, Depends

from app.api.dependencies import DatabaseSession
from app.models.entities import User as UserModel
from app.schemas.loyalty import LoyaltyRewardCatalogRow, LoyaltySettingsRead, LoyaltySettingsUpdate
from app.services.audit import record_audit
from app.services.auth import require_role
from app.services.loyalty import get_loyalty_settings, reward_catalog, update_loyalty_settings

router = APIRouter(prefix="/loyalty", tags=["loyalty"])


@router.get("/settings", response_model=LoyaltySettingsRead)
async def get_settings(
    database: DatabaseSession,
    _: UserModel = Depends(require_role("admin", "cashier", "manager", "accountant")),
):
    return get_loyalty_settings(database)


@router.patch("/settings", response_model=LoyaltySettingsRead)
async def update_settings(
    data: LoyaltySettingsUpdate,
    database: DatabaseSession,
    # Store-wide loyalty policy — admin/manager only, same bar as manual
    # point adjustments and other sensitive program-level actions.
    current_user: UserModel = Depends(require_role("admin", "manager")),
):
    updated = update_loyalty_settings(
        database,
        min_invoice_total=data.min_invoice_total_for_membership,
        min_invoice_profit=data.min_invoice_profit_for_membership,
        tier_silver_min_spend=data.tier_silver_min_spend,
        tier_gold_min_spend=data.tier_gold_min_spend,
        tier_window_days=data.tier_window_days,
        tier_silver_earn_bonus=data.tier_silver_earn_bonus,
        tier_gold_earn_bonus=data.tier_gold_earn_bonus,
        churn_recovery_coupon_points=data.churn_recovery_coupon_points,
        user_id=current_user.id,
    )
    record_audit(
        database,
        user_id=current_user.id,
        username=current_user.username,
        action="update",
        entity_type="loyalty_settings",
        entity_id=updated.id,
        details=(
            f"min_invoice_total={data.min_invoice_total_for_membership}, "
            f"min_invoice_profit={data.min_invoice_profit_for_membership}, "
            f"tier_silver={data.tier_silver_min_spend}, tier_gold={data.tier_gold_min_spend}, "
            f"tier_window_days={data.tier_window_days}, "
            f"tier_silver_bonus={data.tier_silver_earn_bonus}, tier_gold_bonus={data.tier_gold_earn_bonus}, "
            f"churn_recovery_coupon_points={data.churn_recovery_coupon_points}"
        ),
    )
    return updated


@router.get("/reward-catalog", response_model=list[LoyaltyRewardCatalogRow])
async def get_reward_catalog(
    database: DatabaseSession,
    search: str | None = None,
    _: UserModel = Depends(require_role("admin", "cashier", "manager", "accountant")),
):
    return reward_catalog(database, search=search)
