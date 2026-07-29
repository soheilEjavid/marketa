from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select

from app.api.dependencies import DatabaseSession
from app.models.entities import LoyaltyPointTransaction, Sale, User as UserModel
from app.schemas.customer import CustomerCreate, CustomerRead, CustomerUpdate
from app.schemas.financial import CustomerLedger, PaymentCreate, PaymentRead
from app.schemas.loyalty import (
    LoyaltyAdjustRequest,
    LoyaltyBalanceRead,
    LoyaltyRewardSuggestionRow,
    LoyaltyTransactionRead,
)
from app.services import customers as customer_service
from app.services import financials
from app.services.auth import require_role
from app.services.audit import record_audit
from app.services.loyalty import (
    LoyaltyError,
    POINT_VALUE_TOMAN,
    adjust_points_manually,
    award_points_for_payment,
    customer_tier,
    max_redeemable_points,
    reward_suggestions,
    sweep_expired_points,
)

router = APIRouter(prefix="/customers", tags=["customers"])


@router.get("", response_model=list[CustomerRead])
async def list_customers(
    database: DatabaseSession,
    search: str | None = None,
    active_only: bool = True,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    _: UserModel = Depends(require_role("admin", "cashier", "manager", "accountant")),
):
    return customer_service.list_customers(
        database,
        search=search,
        active_only=active_only,
        offset=offset,
        limit=limit,
    )


@router.post("", response_model=CustomerRead, status_code=status.HTTP_201_CREATED)
async def create_customer(
    data: CustomerCreate,
    database: DatabaseSession,
    current_user: UserModel = Depends(require_role("admin", "cashier", "manager")),
):
    try:
        customer = customer_service.create_customer(database, data)
        record_audit(
            database,
            user_id=current_user.id,
            username=current_user.username,
            action="create",
            entity_type="customer",
            entity_id=customer.id,
            details=f"Created customer {customer.full_name}",
        )
        return customer
    except customer_service.DuplicateNationalIdError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.get("/{customer_id}", response_model=CustomerRead)
async def get_customer(
    customer_id: int,
    database: DatabaseSession,
    _: UserModel = Depends(require_role("admin", "cashier", "manager", "accountant")),
):
    customer = customer_service.get_customer(database, customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    return customer


@router.patch("/{customer_id}", response_model=CustomerRead)
async def update_customer(
    customer_id: int,
    data: CustomerUpdate,
    database: DatabaseSession,
    current_user: UserModel = Depends(require_role("admin", "manager")),
):
    customer = customer_service.get_customer(database, customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    try:
        result = customer_service.update_customer(database, customer, data)
        record_audit(
            database,
            user_id=current_user.id,
            username=current_user.username,
            action="update",
            entity_type="customer",
            entity_id=customer_id,
            details=f"Updated customer {customer.full_name}",
        )
        return result
    except customer_service.DuplicateNationalIdError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/{customer_id}/payments", response_model=PaymentRead, status_code=status.HTTP_201_CREATED)
async def create_customer_payment(
    customer_id: int,
    data: PaymentCreate,
    database: DatabaseSession,
    current_user: UserModel = Depends(require_role("admin", "cashier", "manager", "accountant")),
):
    customer = customer_service.get_customer(database, customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    try:
        sale = database.get(Sale, data.document_id) if data.document_id else None
        payment = financials.record_customer_payment(database, customer, data, commit=False)
        award_points_for_payment(database, customer, sale, data.amount)
        database.commit()
        database.refresh(payment)
        record_audit(
            database,
            user_id=current_user.id,
            username=current_user.username,
            action="payment",
            entity_type="customer_payment",
            entity_id=payment.id,
            details=f"Customer {customer.full_name}, amount={data.amount}",
        )
        return payment
    except financials.FinancialError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get("/{customer_id}/ledger", response_model=CustomerLedger)
async def get_customer_ledger(
    customer_id: int,
    database: DatabaseSession,
    _: UserModel = Depends(require_role("admin", "cashier", "manager", "accountant")),
):
    customer = customer_service.get_customer(database, customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    return {"customer_id": customer.id, "customer_name": customer.full_name, "balance": customer.balance, "entries": financials.customer_ledger(database, customer)}


@router.get("/{customer_id}/loyalty", response_model=LoyaltyBalanceRead)
async def get_customer_loyalty_balance(
    customer_id: int,
    database: DatabaseSession,
    sale_total: Decimal | None = Query(default=None, ge=0),
    _: UserModel = Depends(require_role("admin", "cashier", "manager", "accountant")),
):
    customer = customer_service.get_customer(database, customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    if sweep_expired_points(database, customer) > 0:
        database.commit()
        database.refresh(customer)
    cap = (
        max_redeemable_points(sale_total, customer.loyalty_points_balance)
        if sale_total is not None
        else customer.loyalty_points_balance
    )
    return LoyaltyBalanceRead(
        customer_id=customer.id,
        points_balance=customer.loyalty_points_balance,
        points_value_toman=Decimal(customer.loyalty_points_balance) * POINT_VALUE_TOMAN,
        max_redeemable_points=cap,
        is_member=customer.loyalty_member,
        tier=customer_tier(database, customer),
    )


@router.get("/{customer_id}/loyalty/reward-suggestions", response_model=list[LoyaltyRewardSuggestionRow])
async def get_customer_reward_suggestions(
    customer_id: int,
    database: DatabaseSession,
    _: UserModel = Depends(require_role("admin", "cashier", "manager", "accountant")),
):
    customer = customer_service.get_customer(database, customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    return reward_suggestions(database, customer)


@router.get("/{customer_id}/loyalty/transactions", response_model=list[LoyaltyTransactionRead])
async def get_customer_loyalty_transactions(
    customer_id: int,
    database: DatabaseSession,
    _: UserModel = Depends(require_role("admin", "cashier", "manager", "accountant")),
):
    customer = customer_service.get_customer(database, customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    rows = database.scalars(
        select(LoyaltyPointTransaction)
        .where(LoyaltyPointTransaction.customer_id == customer_id)
        .order_by(LoyaltyPointTransaction.created_at.desc())
    ).all()
    return rows


@router.post("/{customer_id}/loyalty/adjust", response_model=LoyaltyBalanceRead)
async def adjust_customer_loyalty_points(
    customer_id: int,
    data: LoyaltyAdjustRequest,
    database: DatabaseSession,
    # Manual point adjustment is the most sensitive loyalty action —
    # admin/manager only, matching other sensitive manual-override actions.
    current_user: UserModel = Depends(require_role("admin", "manager")),
):
    customer = customer_service.get_customer(database, customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    try:
        updated = adjust_points_manually(
            database, customer, data.delta, reason=data.reason, user_id=current_user.id
        )
    except LoyaltyError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    record_audit(
        database,
        user_id=current_user.id,
        username=current_user.username,
        action="loyalty_adjust",
        entity_type="customer",
        entity_id=updated.id,
        details=f"{'+' if data.delta >= 0 else ''}{data.delta} points — {data.reason}",
    )
    return LoyaltyBalanceRead(
        customer_id=updated.id,
        points_balance=updated.loyalty_points_balance,
        points_value_toman=Decimal(updated.loyalty_points_balance) * POINT_VALUE_TOMAN,
        max_redeemable_points=updated.loyalty_points_balance,
        is_member=updated.loyalty_member,
        tier=customer_tier(database, updated),
    )