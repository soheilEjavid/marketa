from datetime import date

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import DatabaseSession
from typing import Literal

from app.models.entities import User as UserModel
from app.schemas.loyalty import ChurnCouponIssueResult
from app.schemas.expense import NetProfitReport
from app.schemas.reports import (
    BirthdayCustomerRow,
    CashierPerformanceRow,
    ChurnRiskCustomerRow,
    CustomerBalanceSummary,
    CustomerTierRow,
    DailySalesSummary,
    DeadStockRow,
    InflationRateReport,
    InventorySummary,
    LowStockReport,
    LoyaltyLiabilityRow,
    LoyaltyRedemptionRow,
    NearExpiryRow,
    PaymentMethodBreakdown,
    ProductSalesSummary,
    SupplierBalanceSummary,
)
from app.services import reports as report_service
from app.services.audit import record_audit
from app.services.auth import require_role
from app.services.loyalty import issue_churn_recovery_coupons

router = APIRouter(prefix="/reports", tags=["reports"])

# All reports surface financial/margin data (revenue, profit, supplier
# balances) more sensitive than day-to-day cashier duties — matches the
# checks.py/shifts.py READ_ROLES convention of excluding "cashier".
READ_ROLES = ("admin", "manager", "inventory_manager", "accountant")


@router.get("/daily-sales", response_model=list[DailySalesSummary])
async def get_daily_sales(
    database: DatabaseSession,
    from_date: date | None = None,
    to_date: date | None = None,
    _: UserModel = Depends(require_role(*READ_ROLES)),
):
    return report_service.daily_sales_summary(database, from_date=from_date, to_date=to_date)


@router.get("/top-products", response_model=list[ProductSalesSummary])
async def get_top_products(
    database: DatabaseSession,
    limit: int = Query(default=20, ge=1, le=100),
    sort_by: Literal["quantity", "profit", "revenue"] = "revenue",
    _: UserModel = Depends(require_role(*READ_ROLES)),
):
    return report_service.top_products(database, limit=limit, sort_by=sort_by)


@router.get("/payment-methods", response_model=list[PaymentMethodBreakdown])
async def get_payment_method_breakdown(
    database: DatabaseSession,
    from_date: date | None = None,
    to_date: date | None = None,
    _: UserModel = Depends(require_role(*READ_ROLES)),
):
    return report_service.payment_method_breakdown(database, from_date=from_date, to_date=to_date)


@router.get("/low-stock", response_model=list[LowStockReport])
async def get_low_stock(
    database: DatabaseSession,
    _: UserModel = Depends(require_role(*READ_ROLES)),
):
    return report_service.low_stock(database)


@router.get("/inventory", response_model=list[InventorySummary])
async def get_inventory(
    database: DatabaseSession,
    _: UserModel = Depends(require_role(*READ_ROLES)),
):
    return report_service.inventory_summary(database)


@router.get("/dead-stock", response_model=list[DeadStockRow])
async def get_dead_stock(
    database: DatabaseSession,
    lookback_days: int = Query(default=30, ge=1, le=365),
    _: UserModel = Depends(require_role(*READ_ROLES)),
):
    return report_service.dead_stock(database, lookback_days=lookback_days)


@router.get("/near-expiry", response_model=list[NearExpiryRow])
async def get_near_expiry(
    database: DatabaseSession,
    red_days: int = Query(default=7, ge=1, le=365),
    orange_days: int = Query(default=30, ge=1, le=365),
    _: UserModel = Depends(require_role(*READ_ROLES)),
):
    return report_service.near_expiry_products(database, red_days=red_days, orange_days=orange_days)


@router.get("/inflation-rate", response_model=InflationRateReport)
async def get_inflation_rate(
    database: DatabaseSession,
    period1_start: date,
    period1_end: date,
    period2_start: date,
    period2_end: date,
    _: UserModel = Depends(require_role(*READ_ROLES)),
):
    return report_service.inflation_rate(
        database,
        period1_start=period1_start,
        period1_end=period1_end,
        period2_start=period2_start,
        period2_end=period2_end,
    )


@router.get("/net-profit", response_model=NetProfitReport)
async def get_net_profit(
    database: DatabaseSession,
    period_start: date,
    period_end: date,
    # Aggregate payroll total only (no per-employee breakdown) — safe for
    # the same broader admin+manager audience as /expenses, per the doc's
    # explicit note that the aggregate number is less sensitive than the
    # per-employee detail behind /salary-payments (admin-only).
    _: UserModel = Depends(require_role("admin", "manager")),
):
    return report_service.net_profit(database, period_start, period_end)


@router.get("/cashier-performance", response_model=list[CashierPerformanceRow])
async def get_cashier_performance(
    database: DatabaseSession,
    from_date: date | None = None,
    to_date: date | None = None,
    _: UserModel = Depends(require_role(*READ_ROLES)),
):
    return report_service.cashier_performance(database, from_date=from_date, to_date=to_date)


@router.get("/customer-balances", response_model=list[CustomerBalanceSummary])
async def get_customer_balances(
    database: DatabaseSession,
    _: UserModel = Depends(require_role(*READ_ROLES)),
):
    return report_service.customer_balances(database)


@router.get("/supplier-balances", response_model=list[SupplierBalanceSummary])
async def get_supplier_balances(
    database: DatabaseSession,
    _: UserModel = Depends(require_role(*READ_ROLES)),
):
    return report_service.supplier_balances(database)


@router.get("/loyalty-liability", response_model=list[LoyaltyLiabilityRow])
async def get_loyalty_liability(
    database: DatabaseSession,
    _: UserModel = Depends(require_role(*READ_ROLES)),
):
    return report_service.loyalty_liability(database)


@router.get("/loyalty-redemptions", response_model=list[LoyaltyRedemptionRow])
async def get_loyalty_redemptions(
    database: DatabaseSession,
    from_date: date | None = None,
    to_date: date | None = None,
    _: UserModel = Depends(require_role(*READ_ROLES)),
):
    return report_service.loyalty_redemptions(database, from_date=from_date, to_date=to_date)


@router.get("/upcoming-birthdays", response_model=list[BirthdayCustomerRow])
async def get_upcoming_birthdays(
    database: DatabaseSession,
    within_days: int = Query(default=30, ge=1, le=365),
    _: UserModel = Depends(require_role(*READ_ROLES)),
):
    return report_service.upcoming_birthdays(database, within_days=within_days)


@router.get("/churn-risk", response_model=list[ChurnRiskCustomerRow])
async def get_churn_risk_customers(
    database: DatabaseSession,
    _: UserModel = Depends(require_role(*READ_ROLES)),
):
    return report_service.churn_risk_customers(database)


@router.post("/churn-risk/issue-coupons", response_model=list[ChurnCouponIssueResult])
async def post_issue_churn_recovery_coupons(
    database: DatabaseSession,
    # Bulk point-granting is a sensitive, money-adjacent action — admin/
    # manager only, same bar as a manual loyalty adjustment.
    current_user: UserModel = Depends(require_role("admin", "manager")),
):
    issued = issue_churn_recovery_coupons(database, user_id=current_user.id)
    if issued:
        record_audit(
            database,
            user_id=current_user.id,
            username=current_user.username,
            action="churn_recovery_coupons",
            entity_type="loyalty",
            entity_id=None,
            details=f"Issued to {len(issued)} customer(s): " + ", ".join(
                f"{row['customer_name']} (+{row['points']})" for row in issued
            ),
        )
    return issued


@router.get("/customer-tiers", response_model=list[CustomerTierRow])
async def get_customer_tiers(
    database: DatabaseSession,
    _: UserModel = Depends(require_role(*READ_ROLES)),
):
    return report_service.customer_tiers_report(database)