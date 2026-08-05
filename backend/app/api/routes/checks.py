from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.dependencies import DatabaseSession
from app.models.entities import CheckStatus, User as UserModel
from app.schemas.checks import CheckRead, CheckStatusUpdate, CheckSummary
from app.services import checks as check_service
from app.services.audit import record_audit
from app.services.auth import require_role

router = APIRouter(prefix="/checks", tags=["checks"])

READ_ROLES = ("admin", "inventory_manager", "manager", "accountant")
WRITE_ROLES = ("admin", "inventory_manager", "manager")


@router.get("", response_model=list[CheckRead])
async def list_checks(
    database: DatabaseSession,
    status: CheckStatus | None = None,
    sort: str = "due_asc",
    search: str | None = None,
    limit: int = Query(default=200, ge=1, le=1000),
    _: UserModel = Depends(require_role(*READ_ROLES)),
):
    checks = check_service.list_checks(database, status=status, sort=sort, search=search, limit=limit)
    return [check_service.to_check_read(check) for check in checks]


@router.get("/summary", response_model=CheckSummary)
async def get_check_summary(
    database: DatabaseSession,
    _: UserModel = Depends(require_role(*READ_ROLES)),
):
    return check_service.check_totals(database)


@router.patch("/{check_id}/status", response_model=CheckRead)
async def update_check_status(
    check_id: int,
    data: CheckStatusUpdate,
    database: DatabaseSession,
    current_user: UserModel = Depends(require_role(*WRITE_ROLES)),
):
    check = check_service.get_check(database, check_id)
    if check is None:
        raise HTTPException(status_code=404, detail="Check not found")
    old_status = check.check_status
    try:
        updated = check_service.update_check_status(database, check, data.status)
    except check_service.CheckError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    record_audit(
        database,
        user_id=current_user.id,
        username=current_user.username,
        action="status_change",
        entity_type="check",
        entity_id=updated.id,
        details=f"{old_status} -> {updated.check_status}",
    )
    return check_service.to_check_read(updated)
