"""
IBVAP — Tracks API Routes
Track querying endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException

from src.api.auth import require_auth

router = APIRouter()


@router.get("/{track_id}")
async def get_track(track_id: int, user: dict = Depends(require_auth)):
    """Get a specific track's details and trajectory."""
    from src.api.app import get_pipeline

    pipeline = get_pipeline()
    if pipeline:
        for cam_id, cam_pipeline in pipeline.camera_pipelines.items():
            track = cam_pipeline.tracker.get_track(track_id)
            if track:
                return track.to_dict()

    raise HTTPException(status_code=404, detail="Track not found")


@router.get("")
async def list_active_tracks(user: dict = Depends(require_auth)):
    """Get all active tracks across cameras."""
    from src.api.app import get_pipeline

    pipeline = get_pipeline()
    result = []
    if pipeline:
        for cam_id, cam_pipeline in pipeline.camera_pipelines.items():
            for tid, track in cam_pipeline.tracker.active_tracks.items():
                result.append(track.to_dict())
    return result
