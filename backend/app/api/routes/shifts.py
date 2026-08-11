from fastapi import APIRouter, Depends, Query, HTTPException, status

from app.api.dependencies import DatabaseSession
from app.models.entities import User as UserModel
from app.schemas.shifts import ShiftCloseRequest, ShiftOpenRequest, ShiftRead
from app.services import shifts as shift_service
from app.services.audit import record_audit
from app.services.auth import require_role

router = APIRouter(prefix="/shifts", tags=["shifts"])

READ_ROLES = ("admin", "cashier", "manager", "accountant", "inventory_manager")
WRITE_ROLES = ("admin", "cashier", "manager")
# Who may see how the count came out. A shortage or an overage is a
# question about the person who counted, so it is not theirs to read —
# they still open, count and close as before.
RECONCILIATION_ROLES = {"admin", "manager", "accountant"}


def _may_see_reconciliation(user: UserModel) -> bool:
    return user.role in RECONCILIATION_ROLES


@router.get("/current", response_model=ShiftRead | None)
async def get_current_shift(
    database: DatabaseSession,
    current_user: UserModel = Depends(require_role(*READ_ROLES)),
):
    shift = shift_service.get_open_shift(database)
    if shift is None:
        return None
    return shift_service.to_shift_read(
        shift, reveal_reconciliation=_may_see_reconciliation(current_user))


@router.post("/open", response_model=ShiftRead, status_code=status.HTTP_201_CREATED)
async def open_shift(
    data: ShiftOpenRequest,
    database: DatabaseSession,
    current_user: UserModel = Depends(require_role(*WRITE_ROLES)),
):
    try:
        shift = shift_service.open_shift(database, cashier_id=data.cashier_id, opening_cash=data.opening_cash)
    except shift_service.ShiftError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    record_audit(
        database,
        user_id=current_user.id,
        username=current_user.username,
        action="open",
        entity_type="cashier_shift",
        entity_id=shift.id,
        details=f"cashier_id={shift.cashier_id}, opening_cash={shift.opening_cash}",
    )
    return shift_service.to_shift_read(
        shift, reveal_reconciliation=_may_see_reconciliation(current_user))


@router.get("", response_model=list[ShiftRead])
async def list_shifts(
    database: DatabaseSession,
    limit: int = Query(default=200, ge=1, le=1000),
    current_user: UserModel = Depends(require_role(*READ_ROLES)),
):
    reveal = _may_see_reconciliation(current_user)
    return [
        shift_service.to_shift_read(shift, reveal_reconciliation=reveal)
        for shift in shift_service.list_shifts(database, limit=limit)
    ]


@router.post("/{shift_id}/close", response_model=ShiftRead)
async def close_shift(
    shift_id: int,
    data: ShiftCloseRequest,
    database: DatabaseSession,
    current_user: UserModel = Depends(require_role(*WRITE_ROLES)),
):
    shift = shift_service.get_shift(database, shift_id)
    if shift is None:
        raise HTTPException(status_code=404, detail="Shift not found")
    try:
        updated = shift_service.close_shift(database, shift, closing_cash=data.closing_cash, notes=data.notes)
    except shift_service.ShiftError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    record_audit(
        database,
        user_id=current_user.id,
        username=current_user.username,
        action="close",
        entity_type="cashier_shift",
        entity_id=updated.id,
        details=f"expected={updated.expected_cash}, closing={updated.closing_cash}, difference={updated.difference}",
    )
    # The audit row above keeps the real figures for the manager; the
    # response withholds them from whoever just counted the drawer.
    return shift_service.to_shift_read(
        updated, reveal_reconciliation=_may_see_reconciliation(current_user))


@router.get("/{shift_id}", response_model=ShiftRead)
async def get_shift(
    shift_id: int,
    database: DatabaseSession,
    current_user: UserModel = Depends(require_role(*READ_ROLES)),
):
    shift = shift_service.get_shift(database, shift_id)
    if shift is None:
        raise HTTPException(status_code=404, detail="Shift not found")
    return shift_service.to_shift_read(
        shift, reveal_reconciliation=_may_see_reconciliation(current_user))
