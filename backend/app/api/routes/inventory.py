from fastapi import APIRouter, Depends, Query

from app.api.dependencies import DatabaseSession
from app.models.entities import InventoryTransactionType, User as UserModel
from app.schemas.inventory import InventoryTransactionRead
from app.services.auth import require_role
from app.services.inventory import list_transactions

router = APIRouter(prefix="/inventory", tags=["inventory"])


@router.get("/transactions", response_model=list[InventoryTransactionRead])
async def get_inventory_transactions(
    database: DatabaseSession,
    product_id: int | None = None,
    transaction_type: InventoryTransactionType | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    _: UserModel = Depends(require_role("admin", "manager", "inventory_manager", "accountant")),
):
    return list_transactions(
        database,
        product_id=product_id,
        transaction_type=transaction_type,
        offset=offset,
        limit=limit,
    )
