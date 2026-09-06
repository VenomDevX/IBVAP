"""
IBVAP — Statistics API Routes
Dashboard statistics and analytics endpoints.
"""

from fastapi import APIRouter, Depends

from src.api.auth import require_auth
from src.database.db import get_database
from src.database.repository import Repository

router = APIRouter()


@router.get("")
async def get_statistics(user: dict = Depends(require_auth)):
    """Get comprehensive dashboard statistics."""
    from src.api.app import get_pipeline
    pipeline = get_pipeline()

    result = {
        "cameras": {},
        "pipeline": {},
        "database": {},
    }

    # Live pipeline stats
    if pipeline:
        result["pipeline"] = pipeline.get_all_stats()
        result["alert_stats"] = pipeline.alert_engine.get_statistics()

    # Database stats
    try:
        db = get_database()
        session = db.get_session()
        repo = Repository(session)
        result["database"] = repo.get_dashboard_stats()
        session.close()
    except Exception:
        result["database"] = {}

    return result


@router.get("/summary")
async def get_summary(user: dict = Depends(require_auth)):
    """Get a quick summary for the dashboard header."""
    from src.api.app import get_pipeline
    pipeline = get_pipeline()

    summary = {
        "total_cameras": 0,
        "online_cameras": 0,
        "total_alerts": 0,
        "unreviewed_alerts": 0,
        "active_tracks": 0,
        "critical_alerts": 0,
    }

    if pipeline:
        summary["total_cameras"] = len(pipeline.camera_pipelines)
        summary["online_cameras"] = sum(
            1 for p in pipeline.camera_pipelines.values()
            if p.video_source.status.value == "online"
        )
        alert_stats = pipeline.alert_engine.get_statistics()
        summary["total_alerts"] = alert_stats.get("total_alerts", 0)
        summary["unreviewed_alerts"] = alert_stats.get("unreviewed", 0)
        summary["critical_alerts"] = alert_stats.get("by_level", {}).get("critical", 0)
        summary["active_tracks"] = sum(
            p.get_stats().get("active_tracks", 0)
            for p in pipeline.camera_pipelines.values()
        )

    return summary


@router.get("/timeseries")
async def get_timeseries(user: dict = Depends(require_auth)):
    """Get alert counts bucketed by hour for the last 24 hours."""
    from src.api.app import get_pipeline
    import time
    from datetime import datetime

    pipeline = get_pipeline()
    if not pipeline:
        return {"labels": [], "data": []}

    alerts = pipeline.alert_engine._alerts
    now = time.time()
    one_day_ago = now - (24 * 3600)

    # Filter alerts from last 24h
    recent = [a for a in alerts if a.timestamp >= one_day_ago]

    # Bucket by hour
    buckets = {i: 0 for i in range(24)}
    for a in recent:
        hour_diff = int((now - a.timestamp) / 3600)
        if 0 <= hour_diff < 24:
            buckets[23 - hour_diff] += 1

    # Generate labels (e.g. 14:00)
    labels = []
    data = []
    for i in range(24):
        t = now - ((23 - i) * 3600)
        dt = datetime.fromtimestamp(t)
        labels.append(dt.strftime("%H:00"))
        data.append(buckets[i])

    return {"labels": labels, "data": data}
