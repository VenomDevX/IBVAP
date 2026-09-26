"""A moving object must keep one track and one box on screen."""

import numpy as np
import pytest

from src.detection.detection_result import DetectionResult, FrameDetections
from src.tracking.tracker import MultiObjectTracker

FPS = 15


def _drive(tracker, step_px, frames=60):
    """One car-sized box moving right by step_px per analysed frame."""
    ids = set()
    for f in range(frames):
        x = 100 + f * step_px
        det = DetectionResult((x, 400, x + 200, 520), 1, "car", 0.9)
        active = tracker.update(FrameDetections(frame_id=f, camera_id="C", timestamp=f / FPS, detections=[det]))
        ids |= set(active)
    return ids


# 40 px/frame keeps ~0.67 IoU with the previous box and 70 px ~0.48: ordinary traffic
# at a reduced analysis rate. ByteTrack's threshold used to be read as IoU >= 0.7,
# which split these into ~30 tracks each.
@pytest.mark.parametrize("step_px", [10, 40, 70])
def test_moving_object_keeps_one_track(step_px):
    tracker = MultiObjectTracker(max_age=30, min_hits=2, iou_threshold=0.3, frame_rate=FPS)
    assert len(_drive(tracker, step_px)) == 1


def test_lost_track_box_is_not_drawn():
    tracker = MultiObjectTracker(max_age=30, min_hits=2, iou_threshold=0.3, frame_rate=FPS)
    _drive(tracker, 10, frames=10)
    (track,) = tracker.active_tracks.values()
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)

    fresh = MultiObjectTracker.draw_tracks(frame, tracker.active_tracks, now=track.last_seen)
    # One second later the track is still active (it survives short occlusions) but
    # its box is frozen where the object was, so it must not be drawn.
    stale = MultiObjectTracker.draw_tracks(frame, tracker.active_tracks, now=track.last_seen + 1.0)

    assert track.is_active
    assert fresh.any()
    assert not stale.any()
