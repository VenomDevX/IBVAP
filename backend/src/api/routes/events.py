"""
IBVAP — Events API Routes
Event querying and detail endpoints.
"""

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from src.api.auth import require_auth, require_camera_access, scoped_cameras
from src.database.db import get_database
from src.database.repository import Repository

router = APIRouter()


def _serialize_event(event, include_context: bool = False) -> dict:
    result = {
        "event_id": event.event_id,
        "camera_id": event.camera_id,
        "track_id": event.track_id,
        "track_uuid": event.track_uuid,
        "zone_id": event.zone_id,
        "event_type": event.event_type,
        "timestamp": event.timestamp.isoformat() if event.timestamp else None,
        "duration": event.duration,
        "object_type": event.object_type,
        "confidence": event.confidence,
        "risk_score": event.risk_score,
        "risk_level": event.risk_level,
        "state": event.state,
        "opened_at": event.opened_at.isoformat() if event.opened_at else None,
        "last_updated": event.last_updated.isoformat() if event.last_updated else None,
        "closed_at": event.closed_at.isoformat() if event.closed_at else None,
        "score_breakdown": event.score_breakdown or {},
        "contributing_factors": event.contributing_factors,
        "evidence_path": event.evidence_path,
        "evidence_hash": event.evidence_hash,
    }
    if include_context:
        result.update(spatial_context=event.spatial_context, temporal_context=event.temporal_context)
    return result


@router.get("")
async def list_events(
    camera_id: str | None = None,
    event_type: str | None = None,
    risk_level: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0, le=100_000),
    user: dict = Depends(require_auth),
):
    """Get events with optional filters."""
    db = get_database()
    session = db.get_session()
    repo = Repository(session)
    events = repo.get_events(camera_id, event_type, risk_level, limit, offset, allowed_cameras=scoped_cameras(user))
    result = [_serialize_event(e) for e in events]
    session.close()
    return result


@router.get("/query")
async def query_events(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    camera_id: str | None = None,
    event_type: str | None = None,
    risk_level: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    search: str | None = Query(default=None, max_length=200),
    sort_by: Literal["timestamp", "risk_score", "camera_id", "event_type"] = "timestamp",
    sort_order: Literal["asc", "desc"] = "desc",
    user: dict = Depends(require_auth),
):
    """Server-paginated query over the complete event history."""
    session = get_database().get_session()
    try:
        repo = Repository(session)
        filters = dict(
            camera_id=camera_id, event_type=event_type, risk_level=risk_level,
            start_time=start_time, end_time=end_time, search=search,
            allowed_cameras=scoped_cameras(user),
        )
        total = repo.get_event_count(**filters)
        rows = repo.get_events(
            **filters, limit=page_size, offset=(page - 1) * page_size,
            sort_by=sort_by, sort_order=sort_order,
        )
        return {"items": [_serialize_event(row) for row in rows], "page": page, "page_size": page_size, "total": total}
    finally:
        session.close()


@router.get("/count")
async def get_event_count(
    camera_id: str | None = None,
    user: dict = Depends(require_auth),
):
    """Get total event count."""
    db = get_database()
    session = db.get_session()
    repo = Repository(session)
    count = repo.get_event_count(camera_id, allowed_cameras=scoped_cameras(user))
    session.close()
    return {"count": count}


@router.get("/{event_id}")
async def get_event(event_id: str, user: dict = Depends(require_auth)):
    """Get a specific event's full details."""
    db = get_database()
    session = db.get_session()
    try:
        repo = Repository(session)
        event = repo.get_event(event_id)
        if not event:
            raise HTTPException(status_code=404, detail="Event not found")
        require_camera_access(user, event.camera_id)
        result = _serialize_event(event, include_context=True)
        result["evidence"] = [
            {
                "evidence_id": row.id, "type": row.evidence_type,
                "created_at": row.created_at.isoformat(),
                "download_url": f"/api/v1/evidence/{event.event_id}/{row.id}",
            }
            for row in repo.get_event_evidence(event.event_id)
        ]
        return result
    finally:
        session.close()
