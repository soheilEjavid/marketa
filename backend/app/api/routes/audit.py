from fastapi import APIRouter, Depends, Query

from app.api.dependencies import DatabaseSession
from app.models.entities import AuditLog as AuditLogModel
from app.services.auth import get_current_user, require_role
from app.services.audit import list_audit_logs

router = APIRouter(prefix="/audit", tags=["audit"])


class AuditLogEntryRead:
    id: int
    user_id: int | None
    username: str | None
    action: str
    entity_type: str
    entity_id: int | None
    details: str | None
    occurred_at: str

    model_config = {"from_attributes": True}


@router.get("/logs", response_model=list[dict])
async def get_audit_logs(
    database: DatabaseSession,
    _=Depends(require_role("admin", "manager")),
    limit: int = Query(default=100, ge=1, le=500),
    action: str | None = None,
    entity_type: str | None = None,
    entity_id: int | None = None,
):
    logs = list_audit_logs(
        database,
        limit=limit,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
    )
    return [
        {
            "id": log.id,
            "user_id": log.user_id,
            "username": log.username,
            "action": log.action,
            "entity_type": log.entity_type,
            "entity_id": log.entity_id,
            "details": log.details,
            "occurred_at": log.occurred_at.isoformat() if log.occurred_at else None,
        }
        for log in logs
    ]