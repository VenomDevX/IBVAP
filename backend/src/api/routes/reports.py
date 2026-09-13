"""
IBVAP — Reports API Routes
"""

import time
from datetime import datetime

from fastapi import APIRouter, Depends, Response

from src.api.auth import can_access_camera, require_auth, scoped_cameras
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
            if not can_access_camera(user, cam_id):
                continue
            tracks = p.track_manager.get_active_tracks()
            for tid, track in tracks.items():
                if track.risk_score > 0:
                    active_threats.append(
                        {
                            "camera_id": cam_id,
                            "object_type": track.object_type,
                            "risk_level": track.risk_level,
                            "risk_score": track.risk_score,
                        }
                    )

    # 2. Fetch past 24h alerts from db
    try:
        db = get_database()
        session = db.get_session()

        from src.database.models import AlertModel

        query = session.query(AlertModel).filter(AlertModel.timestamp >= datetime.fromtimestamp(one_day_ago))
        allowed = scoped_cameras(user)
        if allowed is not None:
            query = query.filter(AlertModel.camera_id.in_(allowed))
        alerts_24h = query.all()

        alert_data = [
            {
                "alert_id": a.alert_id,
                "camera_id": a.camera_id,
                "event_type": a.event_type,
                "risk_level": a.risk_level,
                "risk_score": a.risk_score,
                "timestamp": a.timestamp.isoformat(),
            }
            for a in alerts_24h
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
            "current_active_threats": len(active_threats),
        },
        "alerts": alert_data,
        "active_threats": active_threats,
    }


@router.get("/daily.pdf")
async def get_daily_pdf(user: dict = Depends(require_auth)):
    """Return a real PDF file instead of browser print-preview HTML."""
    from src.reports.pdf import daily_report_pdf

    report = await get_daily_report(user)
    stamp = datetime.now().strftime("%Y-%m-%d")
    return Response(
        content=daily_report_pdf(report),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="ibvap-report-{stamp}.pdf"'},
    )
