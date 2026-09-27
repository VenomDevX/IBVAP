"""
IBVAP — Video Stream Routes
MJPEG video stream and frame capture endpoints.
"""

import asyncio
import io
import threading
import time

import cv2
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse
from PIL import Image

from src.api.auth import refresh_media_identity, require_auth_media, require_camera_access
from src.api.middleware.input_validator import sanitize_camera_id
from src.api.ratelimit import limiter

router = APIRouter()

# The stream sends every new video frame (the source's own rate while someone
# watches, up to VideoSource.MAX_DISPLAY_FPS) with predicted track boxes drawn
# on it; see CameraPipeline.render_live_frame.
_MAX_STREAM_FPS = 60.0
# ~1 hour hard cap so a forgotten tab cannot pin a connection forever
_MAX_FRAMES = int(60 * 60 * _MAX_STREAM_FPS)
# Output widths a client may ask for. Snapping to a few sizes keeps the shared
# per-camera encode cache small however many viewers connect.
_STREAM_WIDTHS = (480, 640, 960, 1280, 1920)
_STREAM_JPEG_QUALITY = 85
_stream_cache: dict[tuple[str, int], dict] = {}
_stream_cache_guard = threading.Lock()


def _stream_width(requested: int) -> int:
    """Largest allowed width not above the request (smallest allowed if below all)."""
    return max((w for w in _STREAM_WIDTHS if w <= requested), default=_STREAM_WIDTHS[0])


def _encode_jpeg(frame) -> bytes:
    """BGR frame -> JPEG. Pillow's libjpeg-turbo is ~2.5x faster than cv2.imencode
    here (1080p: ~10 ms vs ~25 ms), which is what lets the live view keep up with
    30-60 FPS sources."""
    buffer = io.BytesIO()
    Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)).save(buffer, "JPEG", quality=_STREAM_JPEG_QUALITY)
    return buffer.getvalue()


def _encoded_frame(camera_id: str, cam_pipeline, width: int) -> tuple[int, bytes | None]:
    """Render + encode once per camera/frame/width and share the JPEG across viewers."""
    with _stream_cache_guard:
        cache = _stream_cache.setdefault(
            (camera_id, width),
            {"lock": threading.Lock(), "revision": -1, "jpeg": None},
        )
    with cache["lock"]:
        revision = cam_pipeline.video_source.frame_id
        if cache["jpeg"] is not None and cache["revision"] == revision:
            return revision, cache["jpeg"]
        revision, frame = cam_pipeline.render_live_frame()
        if frame is None:
            return revision, None
        if frame.shape[1] > width:
            height = max(1, round(frame.shape[0] * width / frame.shape[1]))
            frame = cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)
        cache["revision"] = revision
        cache["jpeg"] = _encode_jpeg(frame)
        return revision, cache["jpeg"]


async def generate_mjpeg(camera_id: str, request: Request, user: dict, width: int = _STREAM_WIDTHS[-1]):
    """Async generator that yields MJPEG frames until the client disconnects."""
    from src.api.app import get_pipeline

    pipeline = get_pipeline()
    if not pipeline:
        return
    cam_pipeline = pipeline.get_pipeline(camera_id)
    if not cam_pipeline:
        return

    source = cam_pipeline.video_source
    source.add_viewer()  # decode every frame while someone is watching
    try:
        frames = 0
        checked_at = 0.0
        sent_revision = -1
        next_send = 0.0
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

            # Wait for a video frame this client has not seen, but never send
            # faster than _MAX_STREAM_FPS.
            delay = next_send - time.monotonic()
            if delay > 0:
                await asyncio.sleep(delay)
            if source.frame_id == sent_revision:
                await asyncio.sleep(0.004)
                continue

            revision, jpeg = await asyncio.to_thread(_encoded_frame, camera_id, cam_pipeline, width)
            if jpeg is None:
                await asyncio.sleep(0.1)
                continue
            sent_revision = revision
            next_send = time.monotonic() + 1.0 / _MAX_STREAM_FPS
            yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n")
            frames += 1
    finally:
        source.remove_viewer()


@router.get("/{camera_id}")
@limiter.limit("20/minute")
async def video_stream(
    camera_id: str,
    request: Request,
    w: int = Query(1920, ge=1, le=10000, description="Maximum output width in pixels"),
    _user=Depends(require_auth_media),
):
    """Get MJPEG video stream for a camera."""
    camera_id = sanitize_camera_id(camera_id)
    require_camera_access(_user, camera_id)
    from src.api.app import get_pipeline

    pipeline = get_pipeline()

    if not pipeline or camera_id not in pipeline.camera_pipelines:
        raise HTTPException(status_code=404, detail="Camera not found")

    return StreamingResponse(
        generate_mjpeg(camera_id, request, _user, _stream_width(w)),
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

    _, frame = cam_pipeline.render_live_frame()
    if frame is None:
        raise HTTPException(status_code=503, detail="No frame available")

    return Response(content=_encode_jpeg(frame), media_type="image/jpeg")
