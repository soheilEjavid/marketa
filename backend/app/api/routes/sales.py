from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field

from app.api.dependencies import DatabaseSession
from app.models.entities import User as UserModel
from app.schemas.sale import SaleCreate, SaleEditRequest, SaleRead
from app.services import adjustments as adjustment_service
from app.services import sales as sale_service
from app.services.auth import get_current_user, require_role
from app.services.audit import record_audit

router = APIRouter(prefix="/sales", tags=["sales"])


@router.post("", response_model=SaleRead, status_code=status.HTTP_201_CREATED)
async def create_sale(
    data: SaleCreate,
    database: DatabaseSession,
    current_user: UserModel = Depends(require_role("admin", "cashier", "manager")),
):
    try:
        # allow_credit_override is only honored when the authenticated
        # caller's own role (from the JWT, not the request body) is
        # admin/manager — a cashier sending the flag has no effect.
        credit_override_authorized = data.allow_credit_override and current_user.role in ("admin", "manager")
        sale = sale_service.process_sale(database, data, credit_override_authorized=credit_override_authorized)
        record_audit(
            database,
            user_id=current_user.id,
            username=current_user.username,
            action="create",
            entity_type="sale",
            entity_id=sale.id,
            details=f"Invoice {sale.invoice_number}, total={sale.total}",
        )
        return sale
    except sale_service.ProductNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except sale_service.InsufficientStockError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except sale_service.DuplicateInvoiceError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except sale_service.CreditLimitExceededError as error:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "credit_limit_exceeded",
                "message": str(error),
                "current_balance": str(error.current_balance),
                "credit_limit": str(error.credit_limit),
                "credit_portion": str(error.credit_portion),
            },
        ) from error
    except sale_service.SaleError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.post("/hold", response_model=SaleRead, status_code=status.HTTP_201_CREATED)
async def hold_sale(
    data: SaleCreate,
    database: DatabaseSession,
    current_user: UserModel = Depends(require_role("admin", "cashier", "manager")),
):
    try:
        sale = sale_service.hold_sale(database, data)
        record_audit(
            database,
            user_id=current_user.id,
            username=current_user.username,
            action="hold",
            entity_type="sale",
            entity_id=sale.id,
            details=f"Invoice {sale.invoice_number}, total={sale.total}",
        )
        return sale
    except sale_service.ProductNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except sale_service.DuplicateInvoiceError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except sale_service.SaleError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get("/held", response_model=list[SaleRead])
async def list_held_sales(
    database: DatabaseSession,
    _: UserModel = Depends(require_role("admin", "cashier", "manager")),
):
    return sale_service.list_held_sales(database)


@router.post("/{sale_id}/resume", response_model=SaleRead)
async def resume_sale(
    sale_id: int,
    database: DatabaseSession,
    current_user: UserModel = Depends(require_role("admin", "cashier", "manager")),
):
    sale = sale_service.get_sale(database, sale_id)
    if sale is None:
        raise HTTPException(status_code=404, detail="Sale not found")
    try:
        updated = sale_service.cancel_held_sale(database, sale)
    except sale_service.SaleError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    record_audit(
        database,
        user_id=current_user.id,
        username=current_user.username,
        action="resume",
        entity_type="sale",
        entity_id=updated.id,
        details=f"Invoice {updated.invoice_number} resumed for completion under a new invoice",
    )
    return updated


@router.post("/{sale_id}/discard", response_model=SaleRead)
async def discard_sale(
    sale_id: int,
    database: DatabaseSession,
    current_user: UserModel = Depends(require_role("admin", "cashier", "manager")),
):
    sale = sale_service.get_sale(database, sale_id)
    if sale is None:
        raise HTTPException(status_code=404, detail="Sale not found")
    try:
        updated = sale_service.cancel_held_sale(database, sale)
    except sale_service.SaleError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    record_audit(
        database,
        user_id=current_user.id,
        username=current_user.username,
        action="discard",
        entity_type="sale",
        entity_id=updated.id,
        details=f"Invoice {updated.invoice_number} discarded",
    )
    return updated


@router.get("", response_model=list[SaleRead])
async def list_sales(
    database: DatabaseSession,
    response: Response,
    search: str | None = None,
    sort: str = "date_desc",
    offset: int = 0,
    limit: int = 100,
    include_cancelled: bool = False,
    current_user: UserModel = Depends(require_role("admin", "cashier", "manager", "accountant")),
):
    # Only the people who can void an invoice can see the voided ones. A
    # cashier asking for them is not refused, just answered with the same
    # list they always get — the flag is a manager's view, not a permission
    # to trip over mid-shift.
    show_cancelled = include_cancelled and current_user.role in {"admin", "manager"}
    response.headers["X-Total-Count"] = str(
        sale_service.count_sales(database, search=search, include_cancelled=show_cancelled)
    )
    return sale_service.list_sales(
        database, search=search, sort=sort, offset=offset, limit=limit,
        include_cancelled=show_cancelled,
    )


@router.get("/{sale_id}", response_model=SaleRead)
async def get_sale(
    sale_id: int,
    database: DatabaseSession,
    _: UserModel = Depends(require_role("admin", "cashier", "manager", "accountant")),
):
    sale = sale_service.get_sale(database, sale_id)
    if sale is None:
        raise HTTPException(status_code=404, detail="Sale not found")
    return sale


@router.patch("/{sale_id}", response_model=SaleRead)
async def edit_sale(
    sale_id: int,
    data: SaleEditRequest,
    database: DatabaseSession,
    # TODO(security): should be manager-only once real roles/permissions
    # exist — editing a past invoice is more sensitive than creating one.
    current_user: UserModel = Depends(require_role("admin", "manager")),
):
    sale = sale_service.get_sale(database, sale_id)
    if sale is None:
        raise HTTPException(status_code=404, detail="Sale not found")
    try:
        updated, audit_details = sale_service.edit_sale(database, sale, data)
        record_audit(
            database,
            user_id=current_user.id,
            username=current_user.username,
            action="edit",
            entity_type="sale",
            entity_id=updated.id,
            details=audit_details,
        )
        return updated
    except sale_service.ProductNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except sale_service.InsufficientStockError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except sale_service.SaleError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


class CancelSaleInput(BaseModel):
    """A reason is mandatory. Voiding an invoice is the most destructive
    thing this app lets anyone do to the books, and the audit row is worth
    nothing without saying why — same stance as a manual loyalty adjustment
    and an invoice edit."""

    reason: str = Field(min_length=1, max_length=500)
    # Omitted means "the way it was paid" — see adjustments._tender_to_refund.
    # Only set this when the money genuinely goes back another way.
    refund_method: Literal["cash", "card", "card_to_card", "check"] | None = None


@router.post("/{sale_id}/cancel", response_model=SaleRead)
async def cancel_sale(
    sale_id: int,
    data: CancelSaleInput,
    database: DatabaseSession,
    # Same gate as editing a past invoice, for the same reason: this rewrites
    # history. A cashier who rang up the wrong thing asks a manager.
    current_user: UserModel = Depends(require_role("admin", "manager")),
):
    sale = sale_service.get_sale(database, sale_id)
    if sale is None:
        raise HTTPException(status_code=404, detail="Sale not found")
    # Captured before the reversal, which zeroes the invoice — reading it
    # afterwards recorded "total was 0.00", losing the one figure the audit
    # row exists to preserve.
    invoice_number, invoice_total = sale.invoice_number, sale.total
    try:
        updated = adjustment_service.cancel_sale(
            database, sale, reason=data.reason, refund_method=data.refund_method
        )
        record_audit(
            database,
            user_id=current_user.id,
            username=current_user.username,
            action="cancel",
            entity_type="sale",
            entity_id=sale_id,
            details=f"Invoice {invoice_number} cancelled, total was {invoice_total}: {data.reason}",
        )
        return updated
    except adjustment_service.AdjustmentError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
