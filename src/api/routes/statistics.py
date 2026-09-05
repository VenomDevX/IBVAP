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
