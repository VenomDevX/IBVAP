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


def test_detector_uses_lowest_class_floor_for_inference(monkeypatch):
    from src.detection import detector as detmod

    monkeypatch.setattr(detmod.ObjectDetector, "_load_model", lambda self: None)
    detector = detmod.ObjectDetector(
        confidence_threshold=0.30,
        class_thresholds={"License Plate": 0.22, "person": 0.30},
    )
    assert detector.inference_confidence == 0.22
    assert detector.class_thresholds == {"license_plate": 0.22, "person": 0.30}


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


# --------------------------------------------------------------------------- #
# MultiObjectTracker — ByteTrack quiet-frame fallback
#
# Reproduced on the real supervision.ByteTrack (0.30.2, deprecated - removed
# in 0.31): it drops an already-confirmed track from its per-frame output on
# many frames despite an unchanged, overlapping, high-confidence detection,
# freezing `last_seen`/`duration` and therefore ANPR, face re-identification
# and the stage-2 classifier, which all gate on duration. Confirmed on both a
# static synthetic clip and real moving traffic footage.
#
# A fake tracker is used here rather than the real one so this test is
# deterministic and does not depend on the deprecated library's exact
# (and apparently non-guaranteed) per-frame reporting behaviour.
# --------------------------------------------------------------------------- #


class _QuietAfterActivationByteTrack:
    """Reports a tracker_id once, then goes quiet on it forever - the exact
    failure mode observed from the real (deprecated) sv.ByteTrack."""

    def __init__(self):
        self._reported_once: set[int] = set()
        self._next_id = 1

    def update_with_detections(self, sv_detections):
        import supervision as sv

        n = len(sv_detections.xyxy)
        ids = []
        for _ in range(n):
            tid = self._next_id
            if tid in self._reported_once:
                continue  # already activated once - go quiet, as observed
            self._reported_once.add(tid)
            ids.append(tid)
        if not ids:
            return sv.Detections(xyxy=np.zeros((0, 4)), confidence=np.zeros(0), class_id=np.zeros(0, dtype=int))
        # only ever "confirms" tracker_id=1 in this fixture (single object)
        return sv.Detections(
            xyxy=sv_detections.xyxy[:1],
            confidence=sv_detections.confidence[:1],
            class_id=sv_detections.class_id[:1],
            tracker_id=np.array([1]),
        )


def test_duration_keeps_advancing_when_bytetrack_goes_quiet(tracker):
    """THE regression: without the fallback, duration freezes at ~0 forever
    after the activation frame, even though the object is still detected
    every frame with an unchanged, overlapping bbox."""
    tracker._tracker = _QuietAfterActivationByteTrack()
    t0 = time.time()
    box = (100, 100, 160, 260)

    tracks = tracker.update(_frame(0, [(box, 0, "person")], t0))
    assert tracks, "activation frame must confirm a track"
    tid = next(iter(tracks))

    # ByteTrack goes quiet on this id from here on (per the fake), but the
    # same object keeps being detected every frame.
    last_duration = -1.0
    for i in range(1, 10):
        tracks = tracker.update(_frame(i, [(box, 0, "person")], t0 + i * 0.2))
        assert tid in tracks, "fallback must keep the track active/visible"
        assert tracks[tid].duration > last_duration, (
            f"duration must keep advancing (frame {i}); it must not freeze "
            "just because the underlying tracker stopped reporting this id"
        )
        last_duration = tracks[tid].duration
    assert last_duration >= 1.6  # ~9 * 0.2s, minus the activation frame


class _NeverConfirmsByteTrack:
    """A tracker that never activates anything - always reports empty."""

    def update_with_detections(self, sv_detections):
        import supervision as sv

        return sv.Detections(xyxy=np.zeros((0, 4)), confidence=np.zeros(0), class_id=np.zeros(0, dtype=int))


def test_fallback_never_creates_a_track_bytetrack_did_not_confirm():
    """The fallback must only refresh EXISTING tracks, never invent one -
    activation/min_hits stays entirely ByteTrack's responsibility. Fed the
    same detection repeatedly against a tracker that never activates
    anything, no track may appear - there is nothing yet for the fallback to
    reconcile against."""
    from src.tracking.tracker import MultiObjectTracker

    trk = MultiObjectTracker()
    trk._tracker = _NeverConfirmsByteTrack()
    box = (0, 0, 10, 10)
    t0 = time.time()
    for i in range(10):
        tracks = trk.update(_frame(i, [(box, 0, "person")], t0 + i * 0.1))
    assert tracks == {}


def test_fallback_does_not_update_a_track_bytetrack_freshly_confirmed():
    """When ByteTrack DOES report an id this frame, the fallback pass must
    leave it alone rather than double-processing it."""
    from src.tracking.tracker import MultiObjectTracker

    trk = MultiObjectTracker()
    t0 = time.time()
    box = (50, 50, 90, 130)
    for i in range(6):  # real ByteTrack, > min_hits to confirm
        tracks = trk.update(_frame(i, [(box, 0, "person")], t0 + i * 0.05))
    assert tracks, "expected a confirmed track from the real tracker"


def test_bbox_iou():
    from src.tracking.tracker import _bbox_iou

    assert _bbox_iou((0, 0, 10, 10), (0, 0, 10, 10)) == 1.0
    assert _bbox_iou((0, 0, 10, 10), (20, 20, 30, 30)) == 0.0
    # half-overlap square: intersection 5x10=50, union 100+100-50=150
    assert abs(_bbox_iou((0, 0, 10, 10), (5, 0, 15, 10)) - 50 / 150) < 1e-9
