from fastapi import APIRouter, Depends
from app.api.dependencies import DatabaseSession
from app.models.entities import User as UserModel
from app.schemas.dashboard import DashboardSummary
from app.services.auth import require_role
from app.services.dashboard import get_summary
router = APIRouter(prefix="/dashboard", tags=["dashboard"])
@router.get("/summary", response_model=DashboardSummary)
async def dashboard_summary(
    database: DatabaseSession,
    # Any authenticated role — this is the landing page every role sees.
    _: UserModel = Depends(require_role("admin", "cashier", "manager", "accountant", "inventory_manager")),
):
    return get_summary(database)
