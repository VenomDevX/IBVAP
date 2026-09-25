"""
IBVAP — Video Stream Routes
MJPEG video stream and frame capture endpoints.
"""

import asyncio
import threading
import time

import cv2
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response, StreamingResponse

from src.api.auth import refresh_media_identity, require_auth_media, require_camera_access
from src.api.middleware.input_validator import sanitize_camera_id
from src.api.ratelimit import limiter

router = APIRouter()

# ~1 hour hard cap so a forgotten tab cannot pin a connection forever
_MAX_FRAMES = 60 * 60 * 30
_STREAM_FPS = 15.0  # Smoother motion (was 10)
_STREAM_MAX_WIDTH = 1280  # Higher resolution (was 960)
_STREAM_JPEG_QUALITY = 80  # Sharper image (was 65)
_stream_cache: dict[str, dict] = {}
_stream_cache_guard = threading.Lock()


def _encoded_frame(camera_id: str, cam_pipeline) -> bytes | None:
    """Encode once per camera/frame and share the JPEG across all viewers."""
    with _stream_cache_guard:
        cache = _stream_cache.setdefault(
            camera_id,
            {"lock": threading.Lock(), "revision": -1, "jpeg": None},
        )
    with cache["lock"]:
        revision = cam_pipeline.get_stats().get("frames_processed", 0)
        if cache["jpeg"] is not None and cache["revision"] == revision:
            return cache["jpeg"]
        frame = cam_pipeline.get_latest_annotated_frame()
        if frame is None:
            frame = cam_pipeline.get_latest_frame()
        if frame is None:
            return None
        if frame.shape[1] > _STREAM_MAX_WIDTH:
            height = max(1, round(frame.shape[0] * _STREAM_MAX_WIDTH / frame.shape[1]))
            frame = cv2.resize(frame, (_STREAM_MAX_WIDTH, height), interpolation=cv2.INTER_AREA)
        ok, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, _STREAM_JPEG_QUALITY])
        if not ok:
            return None
        cache["revision"] = revision
        cache["jpeg"] = buffer.tobytes()
        return cache["jpeg"]


async def generate_mjpeg(camera_id: str, request: Request, user: dict):
    """Async generator that yields MJPEG frames until the client disconnects."""
    from src.api.app import get_pipeline

    pipeline = get_pipeline()
    if not pipeline:
        return
    cam_pipeline = pipeline.get_pipeline(camera_id)
    if not cam_pipeline:
        return

    frames = 0
    checked_at = 0.0
    while frames < _MAX_FRAMES:
        if await request.is_disconnected():
            break

        if time.time() - checked_at >= 1:
            try:
                user = refresh_media_identity(user)
                require_camera_access(user, camera_id)
            except HTTPException:
                break
            checked_at = time.time()

        jpeg = await asyncio.to_thread(_encoded_frame, camera_id, cam_pipeline)
        if jpeg is not None:
            yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n")
            frames += 1
            await asyncio.sleep(1.0 / _STREAM_FPS)
        else:
            await asyncio.sleep(0.1)


@router.get("/{camera_id}")
@limiter.limit("20/minute")
async def video_stream(camera_id: str, request: Request, _user=Depends(require_auth_media)):
    """Get MJPEG video stream for a camera."""
    camera_id = sanitize_camera_id(camera_id)
    require_camera_access(_user, camera_id)
    from src.api.app import get_pipeline

    pipeline = get_pipeline()

    if not pipeline or camera_id not in pipeline.camera_pipelines:
        raise HTTPException(status_code=404, detail="Camera not found")

    return StreamingResponse(
        generate_mjpeg(camera_id, request, _user),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "private, no-store"},
    )


@router.get("/{camera_id}/snapshot")
@limiter.limit("60/minute")
async def get_snapshot(camera_id: str, request: Request, _user=Depends(require_auth_media)):
    """Get a single snapshot frame from a camera."""
    camera_id = sanitize_camera_id(camera_id)
    require_camera_access(_user, camera_id)
    from src.api.app import get_pipeline

    pipeline = get_pipeline()

    if not pipeline:
        raise HTTPException(status_code=503, detail="Pipeline not running")

    cam_pipeline = pipeline.get_pipeline(camera_id)
    if not cam_pipeline:
        raise HTTPException(status_code=404, detail="Camera not found")

    frame = cam_pipeline.get_latest_annotated_frame()
    if frame is None:
        frame = cam_pipeline.get_latest_frame()

    if frame is None:
        raise HTTPException(status_code=503, detail="No frame available")

    _, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return Response(content=buffer.tobytes(), media_type="image/jpeg")
