"""
IBVAP — Alerts API Routes
Alert querying, review, and management endpoints.
"""

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.api.auth import can_access_camera, require_auth, require_camera_access, require_role, scoped_cameras
from src.database.db import get_database
from src.database.repository import Repository

router = APIRouter()


class IncidentUpdate(BaseModel):
    status: Literal["open", "acknowledged", "investigating", "resolved", "false_positive", "reopened"] | None = None
    disposition: Literal["true_alarm", "false_alarm", "test", "escalated"] | None = None
    assignee: str | None = Field(default=None, max_length=100)
    note: str | None = Field(default=None, max_length=4000)
    false_positive_reason: Literal[
        "Wrong object detection", "Duplicate alert", "Authorized person", "Authorized vehicle",
        "Incorrect zone", "Behavior incorrectly classified", "Other",
    ] | None = None


def _serialize_alert(alert) -> dict:
    return {
        "alert_id": alert.alert_id,
        "camera_id": alert.camera_id,
        "event_id": alert.event_id,
        "track_id": alert.track_id,
        "event_type": alert.event_type,
        "timestamp": alert.timestamp.isoformat() if alert.timestamp else None,
        "risk_score": alert.risk_score,
        "risk_level": alert.risk_level,
        "object_type": alert.object_type,
        "contributing_factors": alert.contributing_factors,
        "snapshot_path": alert.snapshot_path,
        "snapshot_hash": alert.snapshot_hash,
        "reviewed": alert.reviewed,
        "reviewed_by": alert.reviewed_by,
        "reviewed_at": alert.reviewed_at.isoformat() if alert.reviewed_at else None,
        "status": alert.status,
        "disposition": alert.disposition,
        "assignee": alert.assignee,
        "acknowledged_at": alert.acknowledged_at.isoformat() if alert.acknowledged_at else None,
        "resolved_at": alert.resolved_at.isoformat() if alert.resolved_at else None,
        "acknowledged_by": alert.acknowledged_by,
        "resolved_by": alert.resolved_by,
        "false_positive": alert.false_positive,
    }


@router.get("")
async def list_alerts(
    camera_id: str | None = None,
    risk_level: str | None = None,
    reviewed: bool | None = None,
    limit: int = Query(default=100, le=500),
    user: dict = Depends(require_auth),
):
    """Get alerts with optional filters."""
    db = get_database()
    session = db.get_session()
    repo = Repository(session)
    alerts_list = repo.get_alerts(camera_id, risk_level, reviewed, limit, allowed_cameras=scoped_cameras(user))
    result = [_serialize_alert(a) for a in alerts_list]
    session.close()
    return result


@router.get("/query")
async def query_alerts(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    camera_id: str | None = None,
    risk_level: str | None = None,
    reviewed: bool | None = None,
    status: str | None = None,
    active_only: bool = False,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    search: str | None = Query(default=None, max_length=200),
    sort_by: Literal["priority", "timestamp", "risk_score", "status", "camera_id"] = "priority",
    sort_order: Literal["asc", "desc"] = "desc",
    user: dict = Depends(require_auth),
):
    """Server-paginated incident query over the complete alert history."""
    session = get_database().get_session()
    try:
        repo = Repository(session)
        filters = dict(
            camera_id=camera_id, risk_level=risk_level, reviewed=reviewed, status=status,
            active_only=active_only,
            start_time=start_time, end_time=end_time, search=search,
            allowed_cameras=scoped_cameras(user),
        )
        total = repo.count_alerts(**filters)
        rows = repo.get_alerts(
            **filters, limit=page_size, offset=(page - 1) * page_size,
            sort_by=sort_by, sort_order=sort_order,
        )
        return {"items": [_serialize_alert(row) for row in rows], "page": page, "page_size": page_size, "total": total}
    finally:
        session.close()


@router.get("/live")
async def get_live_alerts(user: dict = Depends(require_auth)):
    """Get real-time alerts from the alert engine."""
    from src.api.app import get_pipeline

    pipeline = get_pipeline()
    if pipeline:
        return [a for a in pipeline.alert_engine.get_all_alerts(limit=5000)
                if can_access_camera(user, a["camera_id"])][:50]
    return []


@router.get("/{alert_id}")
async def get_alert(alert_id: str, user: dict = Depends(require_auth)):
    """Get a specific alert's full details."""
    session = get_database().get_session()
    try:
        repo = Repository(session)
        alert = repo.get_alert(alert_id)
        if not alert:
            raise HTTPException(status_code=404, detail="Alert not found")
        require_camera_access(user, alert.camera_id)
        result = _serialize_alert(alert)
        result["notes"] = [
            {"author": note.author, "note": note.note, "created_at": note.created_at.isoformat()}
            for note in alert.notes
        ]
        return result
    finally:
        session.close()


@router.patch("/{alert_id}")
async def update_incident(
    alert_id: str,
    update: IncidentUpdate,
    user: dict = Depends(require_auth),
):
    """Advance an incident and append an immutable operator note."""
    actor = user.get("email") or user.get("user_id") or "unknown"
    role = user.get("app_role")
    requested_status = update.status
    allowed = {"admin", "commander", "supervisor", "operator"} if requested_status in {"resolved", "false_positive", "reopened"} else {
        "admin", "commander", "supervisor", "operator"
    }
    if role not in allowed:
        raise HTTPException(status_code=403, detail="Role cannot perform this incident transition")
    session = get_database().get_session()
    try:
        repo = Repository(session)
        alert = repo.get_alert(alert_id)
        if alert is None:
            raise HTTPException(status_code=404, detail="Alert not found")
        require_camera_access(user, alert.camera_id)
        changes = update.model_dump(exclude_unset=True)
        feedback_reason = changes.pop("false_positive_reason", None)
        updated = repo.update_alert_workflow(alert_id, actor, **changes)
        if update.status == "false_positive":
            repo.create_operator_feedback(updated, actor, feedback_reason or "Other")
            session.commit()
        repo.create_audit_log("update_incident", actor, {"alert_id": alert_id, "changes": changes})
        return _serialize_alert(updated)
    finally:
        session.close()


@router.post("/{alert_id}/review")
async def review_alert(alert_id: str, user: dict = Depends(require_role("operator", "commander", "supervisor"))):
    """Mark an alert as reviewed. Attribution comes from the auth token only."""
    actor = user.get("email") or user.get("user_id") or "unknown"
    db = get_database()
    session = db.get_session()
    success = False
    try:
        repo = Repository(session)
        alert = repo.get_alert(alert_id)
        if not alert:
            raise HTTPException(status_code=404, detail="Alert not found")
        require_camera_access(user, alert.camera_id)
        success = repo.mark_alert_reviewed(alert_id, actor)
        if success:
            repo.create_audit_log("review_alert", actor, {"alert_id": alert_id})
    finally:
        session.close()

    if not success:
        raise HTTPException(status_code=404, detail="Alert not found")

    from src.api.app import get_pipeline

    pipeline = get_pipeline()
    if pipeline:
        pipeline.alert_engine.mark_reviewed(alert_id, actor)

    return {"message": "Alert marked as reviewed", "alert_id": alert_id}
