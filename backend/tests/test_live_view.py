"""Live view: full-rate playback while watched, predicted boxes between analyses."""

import time

import cv2
import numpy as np

from src.api.routes.stream import _stream_width
from src.ingestion.video_source import CameraInfo, VideoSource
from src.tracking.tracker import OverlayBox, draw_overlay


def _box(velocity=(0.0, 0.0), last_seen=10.0):
    return OverlayBox(
        track_id=1,
        label="ID:1 car",
        color=(0, 0, 255),
        bbox=(100, 100, 200, 160),
        last_seen=last_seen,
        velocity=velocity,
        trail=np.empty((0, 2), dtype=np.int32),
    )


def _red_columns(frame):
    return np.flatnonzero((frame[:, :, 2] == 255).any(axis=0))


def test_box_is_moved_along_its_velocity():
    frame = np.zeros((300, 600, 3), dtype=np.uint8)
    moving = _box(velocity=(200.0, 0.0))  # 200 px/s to the right

    at_detection = draw_overlay(frame, [moving], now=10.0)
    later = draw_overlay(frame, [moving], now=10.25, max_stale=0.35)  # 0.25 s later -> +50 px

    assert _red_columns(later).min() - _red_columns(at_detection).min() == 50


def test_box_past_max_age_is_not_drawn():
    frame = np.zeros((300, 600, 3), dtype=np.uint8)
    assert not draw_overlay(frame, [_box()], now=10.5, max_stale=0.35).any()


def test_stream_width_snaps_to_allowed_sizes():
    assert _stream_width(1920) == 1920
    assert _stream_width(1000) == 960
    assert _stream_width(99999) == 1920
    assert _stream_width(1) == 480


def _stored_fps(source: VideoSource, seconds: float = 1.0) -> float:
    start_id = source.frame_id
    time.sleep(seconds)
    return (source.frame_id - start_id) / seconds


def test_frames_are_kept_at_source_rate_only_while_watched(tmp_path):
    clip = str(tmp_path / "clip.avi")
    writer = cv2.VideoWriter(clip, cv2.VideoWriter_fourcc(*"MJPG"), 30.0, (160, 90))
    for i in range(90):
        writer.write(np.full((90, 160, 3), i % 255, dtype=np.uint8))
    writer.release()

    source = VideoSource(CameraInfo(camera_id="CAM", name="CAM", source=clip, fps_limit=5))
    assert source.connect()
    try:
        idle = _stored_fps(source)
        source.add_viewer()
        watched = _stored_fps(source)
        source.remove_viewer()
    finally:
        source.release()

    assert idle <= 8  # analysis rate (5 FPS) when nobody watches
    assert watched >= 20  # the clip's own 30 FPS while watched
