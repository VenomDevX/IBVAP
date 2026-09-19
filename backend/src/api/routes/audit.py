"""
IBVAP — Audit API Routes
"""

from fastapi import APIRouter, Depends, Query

from src.api.auth import require_role
from src.database.db import get_database
from src.database.repository import Repository

router = APIRouter()


@router.get("")
async def get_audit_logs(
    limit: int = Query(default=100, le=500),
    actions_only: bool = Query(default=False, description="Only named user actions, not raw requests"),
    user: dict = Depends(require_role("auditor", "commander")),
):
    """Get recent audit logs."""
    db = get_database()
    session = db.get_session()
    repo = Repository(session)

    logs = repo.get_audit_logs(limit=limit, actions_only=actions_only)

    result = [
        {
            "id": log.id,
            "username": log.username,
            "action": log.action,
            "details": log.details,
            "ip_address": log.ip_address,
            # Stored in UTC; the "Z" stops browsers reading it as local time.
            "timestamp": log.timestamp.isoformat() + "Z" if log.timestamp else None,
        }
        for log in logs
    ]

    session.close()
    return result
