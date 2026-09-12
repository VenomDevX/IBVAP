"""
IBVAP — Tracks API Routes
Track querying endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException

from src.api.auth import can_access_camera, require_auth, require_camera_access

router = APIRouter()


@router.get("/{track_id}")
async def get_track(track_id: int, camera_id: str | None = None, user: dict = Depends(require_auth)):
    """Get a specific track's details and trajectory."""
    from src.api.app import get_pipeline

    pipeline = get_pipeline()
    if camera_id:
        require_camera_access(user, camera_id)
    matches = []
    if pipeline:
        for cam_id, cam_pipeline in pipeline.camera_pipelines.items():
            if not can_access_camera(user, cam_id) or (camera_id and cam_id != camera_id):
                continue
            track = cam_pipeline.tracker.get_track(track_id)
            if track:
                matches.append(track.to_dict())
    if len(matches) > 1:
        raise HTTPException(status_code=409, detail="Specify camera_id for this track")
    if matches:
        return matches[0]

    raise HTTPException(status_code=404, detail="Track not found")


@router.get("")
async def list_active_tracks(user: dict = Depends(require_auth)):
    """Get all active tracks across cameras."""
    from src.api.app import get_pipeline

    pipeline = get_pipeline()
    result = []
    if pipeline:
        for cam_id, cam_pipeline in pipeline.camera_pipelines.items():
            if not can_access_camera(user, cam_id):
                continue
            for tid, track in cam_pipeline.tracker.active_tracks.items():
                result.append(track.to_dict())
    return result
