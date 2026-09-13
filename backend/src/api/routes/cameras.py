"""
IBVAP — Camera API Routes
Camera management and status endpoints.
"""


from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator

from src.api.auth import require_admin, require_auth, require_auth_media, require_camera_access, scoped_cameras
from src.api.middleware.input_validator import sanitize_camera_id
from src.api.ratelimit import limiter
from src.database.db import get_database
from src.database.repository import Repository

router = APIRouter()


class CameraCreate(BaseModel):
    camera_id: str = Field(min_length=1, max_length=50, pattern=r"^[A-Za-z0-9_-]+$")
    name: str = Field(min_length=1, max_length=200)
    source: str = Field(min_length=1, max_length=500)
    type: str = Field(default="general", min_length=1, max_length=50)
    location: str = Field(default="", max_length=200)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    enabled: bool = True
    fps_limit: int = Field(default=15, ge=1, le=120)
    resolution: tuple[int, int] | None = None

    @field_validator("source")
    @classmethod
    def safe_source(cls, source: str):
        if any(char in source for char in ("\x00", "\r", "\n")):
            raise ValueError("Invalid camera source")
        return source.strip()

    @field_validator("resolution")
    @classmethod
    def valid_resolution(cls, resolution):
        if resolution and not (160 <= resolution[0] <= 7680 and 120 <= resolution[1] <= 4320):
            raise ValueError("Resolution is outside the supported range")
        return resolution


class CameraUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    source: str | None = Field(default=None, min_length=1, max_length=500)
    type: str | None = Field(default=None, min_length=1, max_length=50)
    location: str | None = Field(default=None, max_length=200)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    enabled: bool | None = None
    fps_limit: int | None = Field(default=None, ge=1, le=120)
    resolution: tuple[int, int] | None = None

    @field_validator("source")
    @classmethod
    def safe_source(cls, source: str | None):
        if source is not None and any(char in source for char in ("\x00", "\r", "\n")):
            raise ValueError("Invalid camera source")
        return source.strip() if source is not None else source

    @field_validator("resolution")
    @classmethod
    def valid_resolution(cls, resolution):
        if resolution and not (160 <= resolution[0] <= 7680 and 120 <= resolution[1] <= 4320):
            raise ValueError("Resolution is outside the supported range")
        return resolution


def _serialize_camera(camera, include_source: bool = False) -> dict:
    result = {
        "camera_id": camera.camera_id,
        "name": camera.name,
        "location": camera.location_label,
        "latitude": camera.latitude,
        "longitude": camera.longitude,
        "type": camera.camera_type,
        "status": camera.status,
        "enabled": camera.enabled,
        "fps_limit": camera.fps_limit,
        "resolution": camera.resolution,
        "last_frame_at": camera.last_frame_at.isoformat() if camera.last_frame_at else None,
        "last_heartbeat": camera.last_heartbeat.isoformat() if camera.last_heartbeat else None,
        "stream_status": camera.stream_status,
    }
    if include_source:
        result["source"] = camera.stream_url
    return result


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
            "fps_limit": c.fps_limit,
            "resolution": c.resolution,
            "last_frame_at": c.last_frame_at.isoformat() if c.last_frame_at else None,
            "last_heartbeat": c.last_heartbeat.isoformat() if c.last_heartbeat else None,
            "stream_status": c.stream_status,
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
                if p.video_source.last_frame_at:
                    cam["last_frame_at"] = datetime.fromtimestamp(
                        p.video_source.last_frame_at, tz=UTC
                    ).isoformat()
                cam["stream_status"] = p.video_source.status.value

    session.close()
    return result


@router.post("", status_code=201)
async def create_camera(camera: CameraCreate, user: dict = Depends(require_admin)):
    session = get_database().get_session()
    try:
        repo = Repository(session)
        if repo.get_camera(camera.camera_id):
            raise HTTPException(status_code=409, detail="Camera ID already exists")
        row = repo.create_camera(
            camera.camera_id, camera.name, camera.source, camera.type, camera.location,
            camera.latitude, camera.longitude, camera.enabled, camera.fps_limit,
            list(camera.resolution) if camera.resolution else None,
        )
        actor = user.get("email") or user.get("user_id") or "unknown"
        repo.create_audit_log("create_camera", actor, {"camera_id": camera.camera_id})
        from src.api.app import get_pipeline
        pipeline = get_pipeline()
        if pipeline:
            await run_in_threadpool(pipeline.configure_camera, row)
        return _serialize_camera(row, include_source=True)
    finally:
        session.close()


@router.get("/{camera_id}/config")
async def get_camera_config(camera_id: str, _user: dict = Depends(require_admin)):
    camera_id = sanitize_camera_id(camera_id)
    session = get_database().get_session()
    try:
        camera = Repository(session).get_camera(camera_id)
        if camera is None:
            raise HTTPException(status_code=404, detail="Camera not found")
        return _serialize_camera(camera, include_source=True)
    finally:
        session.close()


@router.patch("/{camera_id}")
async def update_camera(camera_id: str, update: CameraUpdate, user: dict = Depends(require_admin)):
    camera_id = sanitize_camera_id(camera_id)
    session = get_database().get_session()
    try:
        repo = Repository(session)
        changes = update.model_dump(exclude_unset=True)
        if "resolution" in changes and changes["resolution"] is not None:
            changes["resolution"] = list(changes["resolution"])
        row = repo.update_camera(camera_id, changes)
        if row is None:
            raise HTTPException(status_code=404, detail="Camera not found")
        actor = user.get("email") or user.get("user_id") or "unknown"
        repo.create_audit_log("update_camera", actor, {"camera_id": camera_id, "fields": sorted(changes)})
        from src.api.app import get_pipeline
        pipeline = get_pipeline()
        if pipeline:
            await run_in_threadpool(pipeline.configure_camera, row)
        return _serialize_camera(row, include_source=True)
    finally:
        session.close()


@router.delete("/{camera_id}")
async def retire_camera(camera_id: str, user: dict = Depends(require_admin)):
    camera_id = sanitize_camera_id(camera_id)
    session = get_database().get_session()
    try:
        repo = Repository(session)
        row = repo.retire_camera(camera_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Camera not found")
        actor = user.get("email") or user.get("user_id") or "unknown"
        repo.create_audit_log("retire_camera", actor, {"camera_id": camera_id})
        from src.api.app import get_pipeline
        pipeline = get_pipeline()
        if pipeline:
            await run_in_threadpool(pipeline.remove_camera, camera_id)
        return {"message": "Camera retired", "camera_id": camera_id}
    finally:
        session.close()


@router.post("/{camera_id}/restart")
async def restart_camera(camera_id: str, user: dict = Depends(require_admin)):
    camera_id = sanitize_camera_id(camera_id)
    from src.api.app import get_pipeline
    pipeline = get_pipeline()
    if pipeline is None or not await run_in_threadpool(pipeline.restart_camera, camera_id):
        raise HTTPException(status_code=409, detail="Camera pipeline is not active")
    actor = user.get("email") or user.get("user_id") or "unknown"
    with get_database().get_session() as session:
        Repository(session).create_audit_log("restart_camera", actor, {"camera_id": camera_id})
    return {"message": "Camera restarted", "camera_id": camera_id}


@router.post("/{camera_id}/test")
async def test_camera(camera_id: str, _user: dict = Depends(require_admin)):
    camera_id = sanitize_camera_id(camera_id)
    session = get_database().get_session()
    try:
        camera = Repository(session).get_camera(camera_id)
        if camera is None:
            raise HTTPException(status_code=404, detail="Camera not found")
        source = camera.stream_url
    finally:
        session.close()

    def probe():
        import cv2
        capture = cv2.VideoCapture(source)
        try:
            opened = capture.isOpened()
            frame_ok = bool(capture.read()[0]) if opened else False
            return {"reachable": opened and frame_ok, "opened": opened, "frame_received": frame_ok}
        finally:
            capture.release()

    return await run_in_threadpool(probe)


@router.get("/{camera_id}")
async def get_camera(camera_id: str, user: dict = Depends(require_auth)):
    """Get a specific camera's details and live status."""
    camera_id = sanitize_camera_id(camera_id)
    require_camera_access(user, camera_id)
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
    camera_id = sanitize_camera_id(camera_id)
    require_camera_access(user, camera_id)
    from src.api.app import get_pipeline

    pipeline = get_pipeline()
    if pipeline:
        p = pipeline.get_pipeline(camera_id)
        if p:
            return p.video_source.get_status_dict()
    raise HTTPException(status_code=404, detail="Camera pipeline not found")


@router.get("/{camera_id}/heatmap")
@limiter.limit("30/minute")
async def get_heatmap(
    camera_id: str,
    request: Request,
    window: int = Query(300, ge=10, le=3600),
    user: dict = Depends(require_auth_media),
):
    """Live heatmap PNG for a camera. The image is composited off the event loop."""
    camera_id = sanitize_camera_id(camera_id)
    require_camera_access(user, camera_id)
    import cv2

    from src.api.app import get_pipeline

    pipeline = get_pipeline()
    if pipeline:
        p = pipeline.get_pipeline(camera_id)
        if p and p.heatmap_tracker:
            heatmap_rgba = await run_in_threadpool(p.heatmap_tracker.generate_heatmap, window_seconds=window)
            ok, img_encoded = await run_in_threadpool(cv2.imencode, ".png", heatmap_rgba)
            if ok:
                return Response(content=img_encoded.tobytes(), media_type="image/png")
    raise HTTPException(status_code=404, detail="Camera pipeline or heatmap tracker not found")
