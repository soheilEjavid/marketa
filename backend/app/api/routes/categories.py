from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import DatabaseSession
from app.models.entities import User as UserModel
from app.schemas.category import CategoryCreate, CategoryRead, CategoryUpdate
from app.services import categories as category_service
from app.services.audit import record_audit
from app.services.auth import require_role

router = APIRouter(prefix="/categories", tags=["categories"])

# Broad read access — categories are needed throughout the catalog/POS UI.
READ_ROLES = ("admin", "cashier", "manager", "accountant", "inventory_manager")
# Matches product create/update's role set (categories are catalog data).
WRITE_ROLES = ("admin", "manager")


@router.get("", response_model=list[CategoryRead])
async def list_categories(
    database: DatabaseSession,
    search: str | None = None,
    _: UserModel = Depends(require_role(*READ_ROLES)),
):
    return category_service.list_categories(database, search=search)


@router.post("", response_model=CategoryRead, status_code=status.HTTP_201_CREATED)
async def create_category(
    data: CategoryCreate,
    database: DatabaseSession,
    current_user: UserModel = Depends(require_role(*WRITE_ROLES)),
):
    try:
        category = category_service.create_category(database, data)
        record_audit(
            database,
            user_id=current_user.id,
            username=current_user.username,
            action="create",
            entity_type="category",
            entity_id=category.id,
            details=f"Created category {category.name}",
        )
        return category
    except category_service.DuplicateCategoryNameError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.patch("/{category_id}", response_model=CategoryRead)
async def update_category(
    category_id: int,
    data: CategoryUpdate,
    database: DatabaseSession,
    current_user: UserModel = Depends(require_role(*WRITE_ROLES)),
):
    category = category_service.get_category(database, category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="Category not found")
    try:
        updated = category_service.update_category(database, category, data)
        record_audit(
            database,
            user_id=current_user.id,
            username=current_user.username,
            action="update",
            entity_type="category",
            entity_id=category.id,
            details=f"Updated category {updated.name}",
        )
        return updated
    except category_service.DuplicateCategoryNameError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
