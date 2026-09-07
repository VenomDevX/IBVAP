"""
IBVAP — Video Stream Routes
MJPEG video stream and frame capture endpoints.
"""

import cv2
import time
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse, Response

router = APIRouter()


def generate_mjpeg(camera_id: str):
    """Generator that yields MJPEG frames for streaming."""
    from src.api.app import get_pipeline
    pipeline = get_pipeline()

    if not pipeline:
        return

    cam_pipeline = pipeline.get_pipeline(camera_id)
    if not cam_pipeline:
        return

    while True:
        frame = cam_pipeline.get_latest_annotated_frame()
        if frame is None:
            frame = cam_pipeline.get_latest_frame()

        if frame is not None:
            _, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" +
                buffer.tobytes() +
                b"\r\n"
            )
        else:
            time.sleep(0.1)

        time.sleep(0.033)  # ~30 FPS cap


@router.get("/{camera_id}")
async def video_stream(camera_id: str):
    """Get MJPEG video stream for a camera."""
    from src.api.app import get_pipeline
    pipeline = get_pipeline()

    if not pipeline or camera_id not in pipeline.camera_pipelines:
        raise HTTPException(status_code=404, detail="Camera not found")

    return StreamingResponse(
        generate_mjpeg(camera_id),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@router.get("/{camera_id}/snapshot")
async def get_snapshot(camera_id: str):
    """Get a single snapshot frame from a camera."""
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
