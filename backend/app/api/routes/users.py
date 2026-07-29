from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import DatabaseSession
from app.models.entities import User as UserModel
from app.schemas.users import UserCreate, UserRoleUpdate, UserSummary
from app.services import users as user_service
from app.services.audit import record_audit
from app.services.auth import require_role

router = APIRouter(prefix="/users", tags=["users"])

READ_ROLES = ("admin", "cashier", "manager", "accountant", "inventory_manager")
# User management is deliberately admin-only — creating accounts and
# granting roles is the most sensitive action in the whole app.
WRITE_ROLES = ("admin",)


@router.get("", response_model=list[UserSummary])
async def list_users(
    database: DatabaseSession,
    active_only: bool = True,
    _: UserModel = Depends(require_role(*READ_ROLES)),
):
    return user_service.list_users(database, active_only=active_only)


@router.post("", response_model=UserSummary, status_code=status.HTTP_201_CREATED)
async def create_user(
    data: UserCreate,
    database: DatabaseSession,
    current_user: UserModel = Depends(require_role(*WRITE_ROLES)),
):
    try:
        user = user_service.create_user(database, data)
    except user_service.DuplicateUsernameError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    record_audit(
        database,
        user_id=current_user.id,
        username=current_user.username,
        action="create",
        entity_type="user",
        entity_id=user.id,
        details=f"Created user {user.username} (role={user.role})",
    )
    return user


@router.patch("/{user_id}", response_model=UserSummary)
async def update_user_active(
    user_id: int,
    data: UserRoleUpdate,
    database: DatabaseSession,
    current_user: UserModel = Depends(require_role(*WRITE_ROLES)),
):
    user = user_service.get_user(database, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == current_user.id and not data.is_active:
        raise HTTPException(status_code=422, detail="Cannot deactivate your own account")
    updated = user_service.set_user_active(database, user, data.is_active)
    record_audit(
        database,
        user_id=current_user.id,
        username=current_user.username,
        action="deactivate" if not data.is_active else "reactivate",
        entity_type="user",
        entity_id=updated.id,
        details=f"{'Deactivated' if not data.is_active else 'Reactivated'} user {updated.username}",
    )
    return updated
