from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.dependencies import DatabaseSession
from app.models.entities import User as UserModel
from app.schemas.product import ProductCreate, ProductRead, ProductUpdate
from app.services import products as product_service
from app.services.auth import require_role

router = APIRouter(prefix="/products", tags=["products"])

# Products are read constantly across nearly every page (POS, purchases,
# reports) — any authenticated role can read. Mutations stay admin/manager.
READ_ROLES = ("admin", "cashier", "manager", "accountant", "inventory_manager")
WRITE_ROLES = ("admin", "manager")


@router.get("", response_model=list[ProductRead])
async def list_products(
    database: DatabaseSession,
    search: str | None = None,
    category_id: int | None = None,
    active_only: bool = True,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    _: UserModel = Depends(require_role(*READ_ROLES)),
):
    return product_service.list_products(
        database,
        search=search,
        category_id=category_id,
        active_only=active_only,
        offset=offset,
        limit=limit,
    )


@router.post("", response_model=ProductRead, status_code=status.HTTP_201_CREATED)
async def create_product(
    data: ProductCreate,
    database: DatabaseSession,
    _: UserModel = Depends(require_role(*WRITE_ROLES)),
):
    try:
        return product_service.create_product(database, data)
    except product_service.DuplicateBarcodeError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except product_service.DuplicateSkuError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.get("/{product_id}", response_model=ProductRead)
async def get_product(
    product_id: int,
    database: DatabaseSession,
    _: UserModel = Depends(require_role(*READ_ROLES)),
):
    product = product_service.get_product(database, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@router.patch("/{product_id}", response_model=ProductRead)
async def update_product(
    product_id: int,
    data: ProductUpdate,
    database: DatabaseSession,
    current_user: UserModel = Depends(require_role("admin", "manager")),
):
    product = product_service.get_product(database, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    try:
        # If collapsing, use the dedicated service function for audit trail
        if data.collapse_to_tier and product.is_dual_priced:
            return product_service.collapse_dual_pricing(
                database,
                product,
                keep_tier=data.collapse_to_tier,
                user_id=current_user.id,
                username=current_user.username,
            )
        return product_service.update_product(database, product, data)
    except product_service.DuplicateBarcodeError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except product_service.DuplicateSkuError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.delete("/{product_id}", response_model=ProductRead)
async def delete_product(
    product_id: int,
    database: DatabaseSession,
    _: UserModel = Depends(require_role(*WRITE_ROLES)),
):
    product = product_service.get_product(database, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return product_service.deactivate_product(database, product)


@router.post("/{product_id}/dual-price/collapse", response_model=ProductRead)
async def collapse_dual_price(
    product_id: int,
    keep_tier: str = Query(..., description="Which tier to keep: 'old' or 'new'"),
    database: DatabaseSession = None,
    current_user: UserModel = Depends(require_role(*WRITE_ROLES)),
):
    """Collapse a dual-priced product back to a single price, keeping the specified tier."""
    product = product_service.get_product(database, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    if not product.is_dual_priced:
        raise HTTPException(status_code=400, detail="Product is not in dual-price mode")
    if keep_tier not in ("old", "new"):
        raise HTTPException(status_code=422, detail="keep_tier must be 'old' or 'new'")
    return product_service.collapse_dual_pricing(
        database,
        product,
        keep_tier=keep_tier,
        user_id=current_user.id,
        username=current_user.username,
    )
