"""trigger_classes on zones/fences, bounded per-track state, enrichment worker limits."""

import threading
import time

from src.pipeline.enrichment_worker import EnrichmentWorker
from src.spatial.fence_detector import FenceDetector, FenceLine
from src.spatial.zone_manager import Zone, ZoneManager
from src.tracking.track import Track
from src.tracking.track_manager import TrackManager

SQUARE = [(0, 0), (100, 0), (100, 100), (0, 100)]


def _track(tid=1, object_type="person", camera="a", session="s1", points=((50, -10), (50, 10))):
    track = Track(track_id=tid, object_type=object_type, camera_id=camera, session_id=session)
    track.trajectory = [(x, y, float(i)) for i, (x, y) in enumerate(points)]
    return track


# --------------------------------------------------------------------------- #
# Zones
# --------------------------------------------------------------------------- #


def test_zone_ignores_classes_outside_trigger_list():
    zones = ZoneManager()
    zones.add_zone(Zone("z", "Walkway", "restricted", "a", SQUARE, trigger_classes=["person"]))
    assert zones.check_track_zones("a", (50, 50), "person") == ["z"]
    assert zones.check_track_zones("a", (50, 50), "car") == []
    assert zones.is_in_restricted_zone("a", 50, 50, "person")
    assert not zones.is_in_restricted_zone("a", 50, 50, "animal")


def test_zone_without_trigger_list_applies_to_everything():
    zones = ZoneManager()
    zones.add_zone(Zone("z", "Any", "restricted", "a", SQUARE))
    assert zones.check_track_zones("a", (50, 50), "truck") == ["z"]


def test_zone_trigger_classes_load_from_yaml():
    zones = ZoneManager()
    zones.load_from_config(
        {
            "zones": {
                "a": [
                    {
                        "id": "z",
                        "name": "Z",
                        "type": "restricted",
                        "points": [list(p) for p in SQUARE],
                        "trigger_classes": ["car", "truck"],
                    }
                ]
            }
        }
    )
    assert zones.get_zone("z").trigger_classes == ["car", "truck"]
    assert zones.get_all_zones()[0]["trigger_classes"] == ["car", "truck"]


def test_restore_backfills_trigger_classes_for_previously_seeded_zones(tmp_db):
    from src.database.repository import Repository
    from src.pipeline.pipeline import IBVAPPipeline

    config = {
        "zones": {
            "a": [
                {
                    "id": "walk",
                    "name": "Walk",
                    "type": "restricted",
                    "points": [list(p) for p in SQUARE],
                    "trigger_classes": ["person"],
                }
            ]
        }
    }
    with tmp_db.get_session() as session:
        repo = Repository(session)
        repo.create_camera("a", "A", "test")
        # Row seeded by an older build that did not store trigger_classes.
        repo.create_zone({"zone_id": "walk", "camera_id": "a", "name": "Walk", "points": [list(p) for p in SQUARE]})

    pipeline = IBVAPPipeline()
    pipeline._restore_zones(config)
    assert pipeline.zone_manager.get_zone("walk").trigger_classes == ["person"]
    with tmp_db.get_session() as session:
        assert Repository(session).get_zones()[0].trigger_classes == ["person"]


# --------------------------------------------------------------------------- #
# Fences
# --------------------------------------------------------------------------- #


def _fence(**kwargs):
    return FenceLine("f", "Fence", "a", (0, 0), (100, 0), **kwargs)


def test_fence_crossing_respects_trigger_classes():
    fences = FenceDetector()
    fences.add_fence(_fence(trigger_classes=["person"]))
    assert fences.check_crossing(_track(1, "animal")) == []
    assert fences.check_approaching(_track(1, "animal")) == []
    events = fences.check_crossing(_track(2, "person"))
    assert [e.fence_id for e in events] == ["f"]


def test_fence_reports_each_track_once_and_history_is_bounded(monkeypatch):
    monkeypatch.setattr(FenceDetector, "MAX_CROSSING_HISTORY", 3)
    fences = FenceDetector()
    fences.add_fence(_fence())
    first = _track(1)
    assert len(fences.check_crossing(first)) == 1
    assert fences.check_crossing(first) == []
    for tid in range(2, 10):
        fences.check_crossing(_track(tid))
    assert len(fences._crossing_history["f"]) == 3
    assert [f.fence_id for f in fences.camera_fences("a")] == ["f"]
    assert fences.camera_fences("b") == []


# --------------------------------------------------------------------------- #
# Track manager
# --------------------------------------------------------------------------- #


def test_track_manager_evicts_closed_tracks():
    manager = TrackManager(expiry_seconds=1.0)
    old = _track(1)
    old.last_seen = time.time() - 60
    manager.update_tracks({1: old})
    assert manager.get_track(1).status == "CLOSED"
    # Once the tracker itself has aged the track out, the manager drops it too.
    manager.update_tracks({})
    assert manager.get_track(1) is None
    assert manager.get_recent_expired() == [old]


def test_track_manager_expiry_survives_numeric_id_reuse():
    manager = TrackManager(expiry_seconds=1.0)
    first = _track(1, session="s1")
    first.last_seen = time.time() - 60
    manager.update_tracks({1: first})

    # After a tracker reset ByteTrack hands out id 1 again for a new object.
    second = _track(1, session="s2")
    second.last_seen = time.time() - 60
    manager.update_tracks({1: second})
    assert manager.get_recent_expired() == [first, second]


# --------------------------------------------------------------------------- #
# Enrichment worker
# --------------------------------------------------------------------------- #


def test_enrichment_worker_bounds_pending_work():
    gate = threading.Event()
    worker = EnrichmentWorker(max_workers=1, max_pending=2)
    try:
        assert worker.submit("t1", "anpr", gate.wait)
        assert worker.submit("t2", "anpr", gate.wait)
        assert not worker.submit("t3", "anpr", gate.wait)
        assert worker.dropped == 1
        # Same key while in flight is deduped, not counted as a drop.
        assert not worker.submit("t1", "anpr", gate.wait)
        assert worker.dropped == 1
    finally:
        gate.set()
        worker.shutdown()


def test_enrichment_worker_rejects_work_after_shutdown():
    worker = EnrichmentWorker()
    worker.shutdown()
    assert worker.submit("t1", "anpr", lambda: None) is False


def test_enrichment_worker_frees_key_after_failure():
    worker = EnrichmentWorker(max_workers=1)
    done = threading.Event()

    def boom():
        raise RuntimeError("x")

    try:
        assert worker.submit("t1", "face", boom)
        deadline = time.time() + 2
        while time.time() < deadline and not worker.submit("t1", "face", done.set):
            time.sleep(0.01)
        assert done.wait(2)
    finally:
        worker.shutdown()
