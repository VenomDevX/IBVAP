"""Coverage for the detect -> track path (which had none).

No model weights required — exercises the dataclasses, taxonomy, the detector's
mock-mode fallback, and the tracker's class mapping / lifecycle / eviction.
"""

import time

import numpy as np
import pytest

from src.detection.detection_result import DetectionResult, FrameDetections

# --------------------------------------------------------------------------- #
# DetectionResult / FrameDetections
# --------------------------------------------------------------------------- #


def test_detection_result_geometry():
    d = DetectionResult(bbox=(10, 20, 110, 220), class_id=0, class_name="person", confidence=0.9)
    assert d.centroid == (60, 120)
    assert d.width == 100
    assert d.height == 200
    assert d.area == 20000
    assert d.to_dict()["class_name"] == "person"


def test_frame_detections_counts_and_numpy():
    fd = FrameDetections(
        frame_id=1,
        camera_id="c1",
        timestamp=time.time(),
        detections=[
            DetectionResult((0, 0, 10, 10), 0, "person", 0.8),
            DetectionResult((5, 5, 15, 15), 0, "person", 0.7),
            DetectionResult((20, 20, 40, 40), 2, "car", 0.6),
        ],
    )
    assert fd.person_count == 2
    assert fd.vehicle_count == 1
    assert [d.confidence for d in fd.get_by_class("person")] == [0.8, 0.7]

    arr = fd.to_numpy()
    assert arr.shape == (3, 6)
    assert arr[2].tolist()[:4] == [20, 20, 40, 40]
    assert arr[2][5] == 2  # class id

    assert FrameDetections(2, "c1", time.time()).to_numpy().shape == (0, 6)


# --------------------------------------------------------------------------- #
# Coarse taxonomy
# --------------------------------------------------------------------------- #


def test_taxonomy_normalize_and_coarse_map():
    from ml import taxonomy

    assert taxonomy.normalize("Car") == "car"
    assert taxonomy.normalize("License Plate") == "license_plate"
    assert taxonomy.normalize("License_Plate") == "license_plate"
    assert taxonomy.normalize("") == "unknown"
    assert taxonomy.normalize("WeirdThing") == "weirdthing"

    assert taxonomy.NUM_COARSE == len(taxonomy.COARSE_NAMES) == 13
    assert all(0 <= c < taxonomy.NUM_COARSE for c in taxonomy.FINE_TO_COARSE.values())
    assert set(taxonomy.FINE_TO_COARSE) == set(range(len(taxonomy.FINE_NAMES)))


# --------------------------------------------------------------------------- #
# ObjectDetector — mock mode (no weights)
# --------------------------------------------------------------------------- #


def test_detector_mock_mode_returns_empty(monkeypatch):
    from src.detection import detector as detmod

    monkeypatch.setattr(detmod.ObjectDetector, "_load_model", lambda self: None)
    det = detmod.ObjectDetector(model_path="does-not-exist.pt")
    assert det._model is None
    out = det.detect(np.zeros((64, 64, 3), np.uint8), frame_id=7, camera_id="c1")
    assert isinstance(out, FrameDetections)
    assert out.frame_id == 7 and out.detections == []


# --------------------------------------------------------------------------- #
# MultiObjectTracker — class mapping + lifecycle + eviction
# --------------------------------------------------------------------------- #


def _frame(fid, boxes, ts):
    return FrameDetections(
        frame_id=fid,
        camera_id="cam1",
        timestamp=ts,
        detections=[DetectionResult(b, cid, name, 0.9) for (b, cid, name) in boxes],
    )


@pytest.fixture()
def tracker():
    from src.tracking.tracker import MultiObjectTracker

    return MultiObjectTracker()


def test_tracker_creates_track_with_detector_class_name(tracker):
    t0 = time.time()
    box = (100, 100, 160, 260)
    tracks = {}
    for i in range(6):  # > min_hits so ByteTrack confirms it
        tracks = tracker.update(_frame(i, [(box, 0, "person")], t0 + i * 0.05))
    assert tracks, "expected at least one confirmed track"
    tr = next(iter(tracks.values()))
    assert tr.object_type == "person"
    assert tr.camera_id == "cam1"
    assert tr.trajectory_length >= 1


def test_tracker_ages_and_evicts_stale_tracks(tracker):
    t0 = time.time()
    box = (10, 10, 50, 90)
    for i in range(6):
        tracker.update(_frame(i, [(box, 2, "car")], t0 + i * 0.05))
    assert tracker._tracks, "track should exist"

    # jump far past evict_after (10 * max_age/30 s) with no detections
    tracker.update(_frame(99, [], t0 + 3600))
    assert tracker._tracks == {}, "long-dead tracks must be evicted (bounds memory)"


def test_tracker_no_detections_is_safe(tracker):
    assert tracker.update(_frame(0, [], time.time())) == {}
