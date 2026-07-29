from datetime import datetime, UTC

from sqlalchemy.orm import Session

from app.models.entities import AuditLog


def record_audit(
    database: Session,
    *,
    user_id: int | None = None,
    username: str | None = None,
    action: str,
    entity_type: str,
    entity_id: int | None = None,
    details: str | None = None,
) -> AuditLog:
    log = AuditLog(
        user_id=user_id,
        username=username,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details=details,
    )
    database.add(log)
    database.commit()
    return log


def list_audit_logs(
    database: Session,
    *,
    limit: int = 100,
    action: str | None = None,
    entity_type: str | None = None,
    entity_id: int | None = None,
) -> list[AuditLog]:
    from sqlalchemy import select

    query = select(AuditLog).order_by(AuditLog.occurred_at.desc()).limit(limit)
    if action:
        query = query.where(AuditLog.action == action)
    if entity_type:
        query = query.where(AuditLog.entity_type == entity_type)
    if entity_id is not None:
        query = query.where(AuditLog.entity_id == entity_id)
    return list(database.scalars(query))