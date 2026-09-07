"""
IBVAP — Events API Routes
Event querying and detail endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional

from src.api.auth import require_auth
from src.database.db import get_database
from src.database.repository import Repository

router = APIRouter()


@router.get("")
async def list_events(
    camera_id: Optional[str] = None,
    event_type: Optional[str] = None,
    risk_level: Optional[str] = None,
    limit: int = Query(default=100, le=500),
    offset: int = 0,
    user: dict = Depends(require_auth),
):
    """Get events with optional filters."""
    db = get_database()
    session = db.get_session()
    repo = Repository(session)
    events = repo.get_events(camera_id, event_type, risk_level, limit, offset)
    result = [
        {
            "event_id": e.event_id,
            "camera_id": e.camera_id,
            "track_id": e.track_id,
            "event_type": e.event_type,
            "timestamp": e.timestamp.isoformat() if e.timestamp else None,
            "duration": e.duration,
            "object_type": e.object_type,
            "risk_score": e.risk_score,
            "risk_level": e.risk_level,
            "contributing_factors": e.contributing_factors,
            "evidence_path": e.evidence_path,
        }
        for e in events
    ]
    session.close()
    return result


@router.get("/count")
async def get_event_count(
    camera_id: Optional[str] = None,
    user: dict = Depends(require_auth),
):
    """Get total event count."""
    db = get_database()
    session = db.get_session()
    repo = Repository(session)
    count = repo.get_event_count(camera_id)
    session.close()
    return {"count": count}


@router.get("/{event_id}")
async def get_event(event_id: str, user: dict = Depends(require_auth)):
    """Get a specific event's full details."""
    db = get_database()
    session = db.get_session()
    repo = Repository(session)
    event = repo.get_event(event_id)
    session.close()

    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    return {
        "event_id": event.event_id,
        "camera_id": event.camera_id,
        "track_id": event.track_id,
        "event_type": event.event_type,
        "timestamp": event.timestamp.isoformat() if event.timestamp else None,
        "duration": event.duration,
        "object_type": event.object_type,
        "confidence": event.confidence,
        "risk_score": event.risk_score,
        "risk_level": event.risk_level,
        "contributing_factors": event.contributing_factors,
        "spatial_context": event.spatial_context,
        "temporal_context": event.temporal_context,
        "evidence_path": event.evidence_path,
    }
