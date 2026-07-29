from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.dependencies import DatabaseSession
from app.models.entities import User as UserModel
from app.schemas.purchase import PurchaseCreate, PurchaseEditRequest, PurchaseItemRead, PurchaseRead
from app.services import purchases as purchase_service
from app.services.auth import require_role
from app.services.audit import record_audit

router = APIRouter(prefix="/purchases", tags=["purchases"])


@router.post("", response_model=PurchaseRead, status_code=status.HTTP_201_CREATED)
async def create_purchase(
    data: PurchaseCreate,
    database: DatabaseSession,
    current_user: UserModel = Depends(require_role("admin", "inventory_manager", "manager")),
):
    try:
        purchase = purchase_service.process_purchase(database, data)
        record_audit(
            database,
            user_id=current_user.id,
            username=current_user.username,
            action="create",
            entity_type="purchase",
            entity_id=purchase.id,
            details=f"Invoice {purchase.invoice_number}, total={purchase.total}",
        )
        return purchase
    except purchase_service.ProductNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except purchase_service.DuplicateInvoiceError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except purchase_service.DualPriceRequiredError as error:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "dual_price_required",
                "message": str(error),
                "products": error.products_info,
            },
        ) from error
    except purchase_service.PurchaseError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get("", response_model=list[PurchaseRead])
async def list_purchases(
    database: DatabaseSession,
    response: Response,
    search: str | None = None,
    sort: str = "date_desc",
    offset: int = 0,
    limit: int = 100,
    _: UserModel = Depends(require_role("admin", "inventory_manager", "manager", "accountant")),
):
    response.headers["X-Total-Count"] = str(purchase_service.count_purchases(database, search=search))
    return purchase_service.list_purchases(database, search=search, sort=sort, offset=offset, limit=limit)


@router.get("/{purchase_id}", response_model=PurchaseRead)
async def get_purchase(
    purchase_id: int,
    database: DatabaseSession,
    _: UserModel = Depends(require_role("admin", "inventory_manager", "manager", "accountant")),
):
    purchase = purchase_service.get_purchase(database, purchase_id)
    if purchase is None:
        raise HTTPException(status_code=404, detail="Purchase not found")
    return purchase


@router.patch("/{purchase_id}", response_model=PurchaseRead)
async def edit_purchase(
    purchase_id: int,
    data: PurchaseEditRequest,
    database: DatabaseSession,
    # TODO(security): should be manager-only once real roles/permissions
    # exist — editing a past invoice is more sensitive than creating one.
    current_user: UserModel = Depends(require_role("admin", "inventory_manager", "manager")),
):
    purchase = purchase_service.get_purchase(database, purchase_id)
    if purchase is None:
        raise HTTPException(status_code=404, detail="Purchase not found")
    try:
        updated, audit_details = purchase_service.edit_purchase(database, purchase, data)
        record_audit(
            database,
            user_id=current_user.id,
            username=current_user.username,
            action="edit",
            entity_type="purchase",
            entity_id=updated.id,
            details=audit_details,
        )
        return updated
    except purchase_service.ProductNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except purchase_service.PurchaseError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.post("/items/{item_id}/settle-consignment", response_model=PurchaseItemRead)
async def settle_consignment_item(
    item_id: int,
    database: DatabaseSession,
    current_user: UserModel = Depends(require_role("admin", "inventory_manager", "manager", "accountant")),
):
    item = purchase_service.get_purchase_item(database, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Purchase item not found")
    try:
        settled = purchase_service.settle_consignment_item(database, item)
    except purchase_service.ConsignmentError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    record_audit(
        database,
        user_id=current_user.id,
        username=current_user.username,
        action="settle_consignment",
        entity_type="purchase_item",
        entity_id=settled.id,
        details=f"purchase_id={settled.purchase_id}, amount={settled.line_total}",
    )
    return settled
