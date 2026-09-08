"""
IBVAP — Alerts API Routes
Alert querying, review, and management endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional

from src.api.auth import require_auth, scoped_cameras
from src.database.db import get_database
from src.database.repository import Repository

router = APIRouter()


@router.get("")
async def list_alerts(
    camera_id: Optional[str] = None,
    risk_level: Optional[str] = None,
    reviewed: Optional[bool] = None,
    limit: int = Query(default=100, le=500),
    user: dict = Depends(require_auth),
):
    """Get alerts with optional filters."""
    db = get_database()
    session = db.get_session()
    repo = Repository(session)
    alerts_list = repo.get_alerts(camera_id, risk_level, reviewed, limit,
                                 allowed_cameras=scoped_cameras(user))
    result = [
        {
            "alert_id": a.alert_id,
            "camera_id": a.camera_id,
            "event_id": a.event_id,
            "track_id": a.track_id,
            "event_type": a.event_type,
            "timestamp": a.timestamp.isoformat() if a.timestamp else None,
            "risk_score": a.risk_score,
            "risk_level": a.risk_level,
            "object_type": a.object_type,
            "contributing_factors": a.contributing_factors,
            "snapshot_path": a.snapshot_path,
            "snapshot_hash": a.snapshot_hash,
            "reviewed": a.reviewed,
            "reviewed_by": a.reviewed_by,
        }
        for a in alerts_list
    ]
    session.close()
    return result


@router.get("/live")
async def get_live_alerts(user: dict = Depends(require_auth)):
    """Get real-time alerts from the alert engine."""
    from src.api.app import get_pipeline
    pipeline = get_pipeline()
    if pipeline:
        return pipeline.alert_engine.get_all_alerts(limit=50)
    return []


@router.get("/{alert_id}")
async def get_alert(alert_id: str, user: dict = Depends(require_auth)):
    """Get a specific alert's full details."""
    db = get_database()
    session = db.get_session()
    repo = Repository(session)
    alert = repo.get_alert(alert_id)
    session.close()

    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

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
    }


@router.post("/{alert_id}/review")
async def review_alert(alert_id: str, user: dict = Depends(require_auth)):
    """Mark an alert as reviewed. Attribution comes from the auth token only."""
    actor = user.get("email") or user.get("user_id") or "unknown"
    db = get_database()
    session = db.get_session()
    success = False
    try:
        repo = Repository(session)
        success = repo.mark_alert_reviewed(alert_id, actor)
        if success:
            repo.create_audit_log("review_alert", actor, {"alert_id": alert_id})
    finally:
        session.close()

    if not success:
        raise HTTPException(status_code=404, detail="Alert not found")

    return {"message": "Alert marked as reviewed", "alert_id": alert_id}
