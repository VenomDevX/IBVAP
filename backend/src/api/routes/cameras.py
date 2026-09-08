"""
IBVAP — Camera API Routes
Camera management and status endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException
from typing import List

from src.api.auth import require_auth, require_auth_media, scoped_cameras
from src.database.db import get_database
from src.database.repository import Repository

router = APIRouter()


@router.get("")
async def list_cameras(user: dict = Depends(require_auth)):
    """Get all configured cameras."""
    db = get_database()
    session = db.get_session()
    repo = Repository(session)
    allowed = scoped_cameras(user)
    cameras = [c for c in repo.get_all_cameras() if allowed is None or c.camera_id in allowed]
    result = [
        {
            "camera_id": c.camera_id,
            "name": c.name,
            "location": c.location_label,
            "latitude": c.latitude,
            "longitude": c.longitude,
            "type": c.camera_type,
            "status": c.status,
            "enabled": c.enabled,
        }
        for c in cameras
    ]

    # Augment with live pipeline status
    from src.api.app import get_pipeline
    pipeline = get_pipeline()
    if pipeline:
        for cam in result:
            p = pipeline.get_pipeline(cam["camera_id"])
            if p:
                cam["status"] = p.video_source.status.value
                stats = p.get_stats()
                cam["fps"] = round(stats.get("fps", 0), 1)
                cam["active_tracks"] = stats.get("active_tracks", 0)

    session.close()
    return result


@router.get("/{camera_id}")
async def get_camera(camera_id: str, user: dict = Depends(require_auth)):
    """Get a specific camera's details and live status."""
    db = get_database()
    session = db.get_session()
    repo = Repository(session)
    camera = repo.get_camera(camera_id)
    session.close()

    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")

    result = {
        "camera_id": camera.camera_id,
        "name": camera.name,
        "location": camera.location_label,
        "latitude": camera.latitude,
        "longitude": camera.longitude,
        "type": camera.camera_type,
        "status": camera.status,
        "enabled": camera.enabled,
    }

    from src.api.app import get_pipeline
    pipeline = get_pipeline()
    if pipeline:
        p = pipeline.get_pipeline(camera_id)
        if p:
            result.update(p.get_stats())
            result["status"] = p.video_source.status.value

    return result


@router.get("/{camera_id}/status")
async def get_camera_status(camera_id: str, user: dict = Depends(require_auth)):
    """Get camera connection status."""
    from src.api.app import get_pipeline
    pipeline = get_pipeline()
    if pipeline:
        p = pipeline.get_pipeline(camera_id)
        if p:
            return p.video_source.get_status_dict()
    raise HTTPException(status_code=404, detail="Camera pipeline not found")

@router.get("/{camera_id}/heatmap")
async def get_heatmap(camera_id: str, window: int = 300, user: dict = Depends(require_auth_media)):
    """Get live heatmap for a camera (returns PNG)."""
    from src.api.app import get_pipeline
    from fastapi.responses import Response
    import cv2
    
    pipeline = get_pipeline()
    if pipeline:
        p = pipeline.get_pipeline(camera_id)
        if p and p.heatmap_tracker:
            heatmap_rgba = p.heatmap_tracker.generate_heatmap(window_seconds=window)
            _, img_encoded = cv2.imencode('.png', heatmap_rgba)
            return Response(content=img_encoded.tobytes(), media_type="image/png")
    raise HTTPException(status_code=404, detail="Camera pipeline or heatmap tracker not found")
