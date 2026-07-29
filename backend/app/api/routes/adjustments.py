from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.api.dependencies import DatabaseSession
from app.models.entities import User as UserModel
from app.schemas.product import ProductRead
from app.schemas.sale import SaleRead
from app.schemas.purchase import PurchaseRead
from app.services import adjustments as adjustment_service
from app.services.auth import require_role
from app.services.audit import record_audit

router = APIRouter(prefix="/adjustments", tags=["adjustments"])


class StockAdjustmentInput(BaseModel):
    product_id: int
    quantity_change: Decimal = Field(gt=0)
    reason: str | None = None


class StockAdjustmentResult(BaseModel):
    product: ProductRead
    quantity_change: Decimal
    reason: str | None = None


class ReturnItemInput(BaseModel):
    product_id: int
    quantity: Decimal = Field(gt=0)
    reason: str | None = None


class ReturnInput(BaseModel):
    items: list[ReturnItemInput] = Field(min_length=1)


@router.post("/stock", response_model=StockAdjustmentResult, status_code=status.HTTP_200_OK)
async def create_adjustment(
    data: StockAdjustmentInput,
    database: DatabaseSession,
    current_user: UserModel = Depends(require_role("admin", "inventory_manager")),
):
    try:
        product = adjustment_service.adjust_stock(database, data.product_id, data.quantity_change, data.reason)
        record_audit(
            database,
            user_id=current_user.id,
            username=current_user.username,
            action="adjust_stock",
            entity_type="product",
            entity_id=data.product_id,
            details=f"Quantity change: {data.quantity_change}, reason: {data.reason or 'N/A'}",
        )
        return StockAdjustmentResult(product=product, quantity_change=data.quantity_change, reason=data.reason)
    except adjustment_service.ProductNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except adjustment_service.AdjustmentError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.post("/sale-return/{sale_id}", response_model=SaleRead, status_code=status.HTTP_200_OK)
async def return_from_sale(
    sale_id: int,
    data: ReturnInput,
    database: DatabaseSession,
    current_user: UserModel = Depends(require_role("admin", "cashier", "inventory_manager")),
):
    try:
        result = adjustment_service.return_sale_items(database, sale_id, [item.model_dump() for item in data.items])
        record_audit(
            database,
            user_id=current_user.id,
            username=current_user.username,
            action="sale_return",
            entity_type="sale",
            entity_id=sale_id,
            details=f"Returned {len(data.items)} item(s)",
        )
        return result
    except adjustment_service.ProductNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except adjustment_service.AdjustmentError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.post("/purchase-return/{purchase_id}", response_model=PurchaseRead, status_code=status.HTTP_200_OK)
async def return_from_purchase(
    purchase_id: int,
    data: ReturnInput,
    database: DatabaseSession,
    current_user: UserModel = Depends(require_role("admin", "inventory_manager")),
):
    try:
        result = adjustment_service.return_purchase_items(database, purchase_id, [item.model_dump() for item in data.items])
        record_audit(
            database,
            user_id=current_user.id,
            username=current_user.username,
            action="purchase_return",
            entity_type="purchase",
            entity_id=purchase_id,
            details=f"Returned {len(data.items)} item(s)",
        )
        return result
    except adjustment_service.ProductNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except adjustment_service.AdjustmentError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error