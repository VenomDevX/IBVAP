"""
IBVAP — Reports API Routes
"""

from fastapi import APIRouter, Depends
import time
from datetime import datetime
from src.api.auth import require_auth
from src.database.db import get_database

router = APIRouter()

@router.get("/daily")
async def get_daily_report(user: dict = Depends(require_auth)):
    """Aggregates the last 24h of data for PDF/CSV reports."""
    from src.api.app import get_pipeline
    pipeline = get_pipeline()

    now = time.time()
    one_day_ago = now - (24 * 3600)

    # 1. Fetch live threats
    active_threats = []
    if pipeline:
        for cam_id, p in pipeline.camera_pipelines.items():
            tracks = p.track_manager.get_active_tracks()
            for tid, track in tracks.items():
                if track.risk_score > 0:
                    active_threats.append({
                        "camera_id": cam_id,
                        "object_type": track.object_type,
                        "risk_level": track.risk_level,
                        "risk_score": track.risk_score,
                    })

    # 2. Fetch past 24h alerts from db
    try:
        db = get_database()
        session = db.get_session()
        
        from src.database.models import AlertModel
        alerts_24h = session.query(AlertModel).filter(
            AlertModel.timestamp >= datetime.fromtimestamp(one_day_ago)
        ).all()
        
        alert_data = [
            {
                "alert_id": a.alert_id,
                "camera_id": a.camera_id,
                "event_type": a.event_type,
                "risk_level": a.risk_level,
                "risk_score": a.risk_score,
                "timestamp": a.timestamp.isoformat()
            } for a in alerts_24h
        ]
        
        session.close()
    except Exception:
        alert_data = []

    return {
        "generated_at": datetime.now().isoformat(),
        "report_period": "Last 24 Hours",
        "summary": {
            "total_alerts_24h": len(alert_data),
            "critical_alerts_24h": sum(1 for a in alert_data if a["risk_level"] == "critical"),
            "current_active_threats": len(active_threats)
        },
        "alerts": alert_data,
        "active_threats": active_threats
    }
