"""
IBVAP — Statistics API Routes
Dashboard statistics and analytics endpoints.
"""

from fastapi import APIRouter, Depends

from src.api.auth import can_access_camera, require_auth, scoped_cameras
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
        result["pipeline"] = {k: v for k, v in pipeline.get_all_stats().items() if can_access_camera(user, k)}
        result["alert_stats"] = pipeline.alert_engine.get_statistics(scoped_cameras(user))

    # Database stats
    try:
        db = get_database()
        session = db.get_session()
        repo = Repository(session)
        result["database"] = repo.get_dashboard_stats(scoped_cameras(user))
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
        cameras = [p for cam, p in pipeline.camera_pipelines.items() if can_access_camera(user, cam)]
        summary["total_cameras"] = len(cameras)
        summary["online_cameras"] = sum(
            1 for p in cameras if p.video_source.status.value == "online"
        )
        alert_stats = pipeline.alert_engine.get_statistics(scoped_cameras(user))
        summary["total_alerts"] = alert_stats.get("total_alerts", 0)
        summary["unreviewed_alerts"] = alert_stats.get("unreviewed", 0)
        summary["critical_alerts"] = alert_stats.get("by_level", {}).get("critical", 0)
        summary["active_tracks"] = sum(
            p.get_stats().get("active_tracks", 0) for p in cameras
        )

    return summary


@router.get("/timeseries")
async def get_timeseries(user: dict = Depends(require_auth)):
    """Get alert counts bucketed by hour for the last 24 hours."""
    import time
    from datetime import datetime

    from src.api.app import get_pipeline

    pipeline = get_pipeline()
    if not pipeline:
        return {"labels": [], "data": []}

    alerts = list(pipeline.alert_engine._alerts)
    now = time.time()
    one_day_ago = now - (24 * 3600)

    # Filter alerts from last 24h
    recent = [a for a in alerts if a.timestamp >= one_day_ago and can_access_camera(user, a.camera_id)]

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


@router.get("/threats")
async def get_threats(user: dict = Depends(require_auth)):
    """Get active threats and risk scores across all cameras."""
    from src.api.app import get_pipeline

    pipeline = get_pipeline()

    if not pipeline:
        return {"top_threats": [], "camera_distribution": {}}

    all_tracks = []
    distribution = {}

    for cam_id, p in pipeline.camera_pipelines.items():
        if not can_access_camera(user, cam_id):
            continue
        tracks = p.track_manager.get_active_tracks()
        distribution[cam_id] = 0

        for tid, track in tracks.items():
            if track.risk_score > 0:
                distribution[cam_id] += 1
                all_tracks.append(
                    {
                        "track_id": f"{cam_id}-{tid}",
                        "camera_id": cam_id,
                        "object_type": track.object_type,
                        "risk_score": round(track.risk_score, 1),
                        "risk_level": track.risk_level,
                        "risk_factors": track.risk_factors,
                        "duration": round(track.duration, 1),
                    }
                )

    # Sort by risk score descending
    all_tracks.sort(key=lambda x: x["risk_score"], reverse=True)

    return {
        "top_threats": all_tracks[:10],  # Top 10 current threats
        "camera_distribution": distribution,
    }
