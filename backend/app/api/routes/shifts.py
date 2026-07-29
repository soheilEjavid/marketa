from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import DatabaseSession
from app.models.entities import User as UserModel
from app.schemas.shifts import ShiftCloseRequest, ShiftOpenRequest, ShiftRead
from app.services import shifts as shift_service
from app.services.audit import record_audit
from app.services.auth import require_role

router = APIRouter(prefix="/shifts", tags=["shifts"])

READ_ROLES = ("admin", "cashier", "manager", "accountant", "inventory_manager")
WRITE_ROLES = ("admin", "cashier", "manager")


@router.get("/current", response_model=ShiftRead | None)
async def get_current_shift(
    database: DatabaseSession,
    _: UserModel = Depends(require_role(*READ_ROLES)),
):
    shift = shift_service.get_open_shift(database)
    return shift_service.to_shift_read(shift) if shift else None


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
    return shift_service.to_shift_read(shift)


@router.get("", response_model=list[ShiftRead])
async def list_shifts(
    database: DatabaseSession,
    _: UserModel = Depends(require_role(*READ_ROLES)),
):
    return [shift_service.to_shift_read(shift) for shift in shift_service.list_shifts(database)]


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
    return shift_service.to_shift_read(updated)


@router.get("/{shift_id}", response_model=ShiftRead)
async def get_shift(
    shift_id: int,
    database: DatabaseSession,
    _: UserModel = Depends(require_role(*READ_ROLES)),
):
    shift = shift_service.get_shift(database, shift_id)
    if shift is None:
        raise HTTPException(status_code=404, detail="Shift not found")
    return shift_service.to_shift_read(shift)
