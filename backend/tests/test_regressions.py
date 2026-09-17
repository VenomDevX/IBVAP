"""Integration regressions for camera isolation and event lifecycle."""

import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import numpy as np
import pytest
from fastapi import HTTPException

from src.alerts.alert_engine import AlertEngine
from src.behavior.behavior_engine import BehaviorEvent, BehaviorType
from src.fusion.context_fusion import ContextFusion, FusedEvent
from src.ingestion.video_source import CameraInfo
from src.pipeline.pipeline import CameraPipeline, IBVAPPipeline
from src.spatial.fence_detector import FenceDetector
from src.spatial.zone_manager import Zone, ZoneManager
from src.tracking.track import Track


def event(camera="a", **kwargs):
    return FusedEvent(
        event_id=kwargs.pop("event_id", "event"),
        camera_id=kwargs.pop("camera_id", camera),
        track_id=kwargs.pop("track_id", 1),
        timestamp=kwargs.pop("timestamp", time.time()),
        object_type=kwargs.pop("object_type", "person"),
        event_type=kwargs.pop("event_type", "restricted_zone_entry"),
        **kwargs,
    )


@pytest.fixture
def scoped_user(monkeypatch):
    from src.api import auth

    monkeypatch.setattr(auth, "_verify_token", lambda token: {"sub": "scoped", "exp": time.time() + 3600})
    monkeypatch.setattr(auth, "resolve_profile", lambda uid: {"role": "operator", "allowed_areas": ["a"]})
    return {"Authorization": "Bearer scope-token"}


@pytest.fixture
def records(tmp_db):
    from src.database.repository import Repository

    with tmp_db.get_session() as session:
        repo = Repository(session)
        for camera in ("a", "b"):
            repo.create_camera(camera, camera, "test")
            repo.create_event({**event(camera, event_id=f"e-{camera}").to_dict(),
                               "evidence_path": f"outputs/snapshots/{camera}.jpg"})
            repo.create_alert({"alert_id": f"al-{camera}", "event_id": f"e-{camera}",
                               "camera_id": camera, "timestamp": time.time(), "event_type": "intrusion"})
            repo.create_zone({"zone_id": f"z-{camera}", "camera_id": camera, "name": "zone",
                              "points": [[0, 0], [100, 0], [0, 100]]})


@pytest.mark.parametrize("path", [
    "/api/events/e-b", "/api/alerts/al-b", "/api/cameras/b", "/api/cameras/b/status",
    "/api/cameras/b/heatmap", "/api/stream/b", "/api/stream/b/snapshot", "/api/zones/b",
    "/api/tracks/1?camera_id=b",
])
def test_restricted_camera_endpoints(client, records, scoped_user, path):
    assert client.get(path, headers=scoped_user).status_code == 403


def test_scoped_lists_counts_reports_and_review(client, records, scoped_user):
    for path in ("cameras", "events", "alerts", "zones"):
        response = client.get(f"/api/{path}", headers=scoped_user)
        assert response.status_code == 200
        assert {r["camera_id"] for r in response.json()} == {"a"}
    assert client.get("/api/events/count", headers=scoped_user).json() == {"count": 1}
    assert client.get("/api/events/e-a", headers=scoped_user).status_code == 200
    assert client.post("/api/alerts/al-b/review", headers=scoped_user).status_code == 403
    assert client.post("/api/alerts/al-a/review", headers=scoped_user).status_code == 200
    report = client.get("/api/reports/daily", headers=scoped_user).json()
    assert {a["camera_id"] for a in report["alerts"]} == {"a"}
    stats = client.get("/api/statistics", headers=scoped_user).json()["database"]
    assert stats["total_events"] == stats["total_alerts"] == stats["cameras"] == 1


def test_server_pagination_and_incident_workflow(client, records, scoped_user):
    alerts = client.get("/api/alerts/query?page=1&page_size=1", headers=scoped_user)
    assert alerts.status_code == 200
    assert alerts.json()["total"] == 1
    assert [item["camera_id"] for item in alerts.json()["items"]] == ["a"]

    events = client.get("/api/events/query?page=1&page_size=1&search=e-a", headers=scoped_user)
    assert events.status_code == 200
    assert events.json()["total"] == 1

    updated = client.patch(
        "/api/alerts/al-a",
        headers=scoped_user,
        json={"status": "resolved", "disposition": "true_alarm", "assignee": "scoped", "note": "Verified"},
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "resolved"
    detail = client.get("/api/alerts/al-a", headers=scoped_user).json()
    assert detail["reviewed"] is True
    assert detail["notes"][0]["note"] == "Verified"


def test_snapshot_ownership_uses_database(client, records, scoped_user, tmp_path, monkeypatch):
    monkeypatch.setenv("IBVAP_SNAPSHOTS_DIR", str(tmp_path))
    for name in ("a.jpg", "b.jpg", "orphan.jpg"):
        (tmp_path / name).write_bytes(b"image")
    assert client.get("/snapshots/a.jpg", headers=scoped_user).status_code == 200
    assert client.get("/snapshots/b.jpg", headers=scoped_user).status_code == 403
    assert client.get("/snapshots/orphan.jpg", headers=scoped_user).status_code == 403


@pytest.mark.parametrize("failure", ["missing_service", "exception", "missing_profile", "bad_scope", "bad_role"])
def test_profile_resolution_fails_closed(monkeypatch, failure):
    from src.api import auth

    monkeypatch.setattr(auth, "_profile_cache", {})
    service = Mock()
    query = service.table.return_value.select.return_value.eq.return_value.limit.return_value
    query.execute.return_value = SimpleNamespace(data=[{"role": "operator", "allowed_areas": ["a"]}])
    if failure == "exception":
        query.execute.side_effect = RuntimeError("offline")
    elif failure == "missing_profile":
        query.execute.return_value.data = []
    elif failure == "bad_scope":
        query.execute.return_value.data[0]["allowed_areas"] = None
    elif failure == "bad_role":
        query.execute.return_value.data[0]["role"] = "invalid"
    monkeypatch.setattr(auth, "_get_service_client", lambda: None if failure == "missing_service" else service)
    with pytest.raises(HTTPException) as exc:
        auth.resolve_profile("u")
    assert exc.value.status_code in (403, 503)
    assert "u" not in auth._profile_cache


def test_websocket_filters_and_rechecks_scope(monkeypatch):
    from src.api import auth
    from src.api.websocket import WebSocketManager

    monkeypatch.setattr(auth, "_deny_if_revoked", lambda token: None)
    profile = {"role": "operator", "allowed_areas": ["a"]}
    monkeypatch.setattr(auth, "resolve_profile", lambda uid: profile)
    socket = SimpleNamespace(send_text=AsyncMock(), close=AsyncMock())
    manager = WebSocketManager()

    async def scenario():
        await manager.connect(socket, {"token": "t", "user_id": "u", "exp": time.time() + 60})
        await manager.broadcast({"type": "alert", "data": {"camera_id": "b"}})
        socket.send_text.assert_not_called()
        await manager.broadcast({"type": "alert", "data": {"camera_id": "a"}})
        assert socket.send_text.call_count == 1
        profile["allowed_areas"] = ["b"]
        await manager.broadcast({"type": "alert", "data": {"camera_id": "a"}})
        assert socket.send_text.call_count == 1
        manager._identities[id(socket)]["exp"] = time.time() - 1
        await manager.broadcast({"type": "alert", "data": {"camera_id": "b"}})
        socket.close.assert_called_once()
        assert manager.connection_count == 0

    asyncio.run(scenario())


def test_fusion_ids_and_escalation(monkeypatch):
    behavior = BehaviorEvent("b", 1, "a", BehaviorType.RESTRICTED_ZONE_ENTRY, time.time(),
                             contributing_factors=["restricted"])
    engines = [ContextFusion(), ContextFusion()]
    generated = [engine.fuse_events(1, cam, "person", [behavior], {"in_restricted": True}, {})
                 for engine, cam in zip(engines, ("a", "b"))]
    assert generated[0].event_id != generated[1].event_id
    engine, first = engines[0], generated[0]
    first.risk_level = "medium"
    engine.mark_recorded(first)
    second = event(risk_level="medium")
    assert not engine.should_record(second)
    second.risk_level = "critical"
    assert engine.should_record(second)
    second.risk_level = "medium"
    second.event_type = "fence_crossing"
    assert engine.should_record(second)


def test_fusion_deduplicates_tracker_churn_and_keeps_escalation():
    engine = ContextFusion(incident_cooldown=60)
    first = event(camera_id="a", track_id=1, risk_level="medium")
    engine.mark_recorded(first)

    replacement_track = event(camera_id="a", track_id=999, risk_level="medium")
    assert not engine.should_record(replacement_track)

    replacement_track.risk_level = "critical"
    assert engine.should_record(replacement_track)


def test_fusion_enforces_per_camera_persistence_budget():
    engine = ContextFusion(incident_cooldown=1, max_events_per_minute=1)
    first = event(camera_id="a", event_type="one")
    engine.mark_recorded(first)
    assert not engine.should_record(event(camera_id="a", event_type="two"))
    assert engine.should_record(event(camera_id="b", event_type="two"))


def test_alert_dedup_is_camera_scoped_and_escalates(tmp_path):
    engine = AlertEngine(snapshots_dir=str(tmp_path))
    engine.notification_manager.notify_critical = Mock()
    assert engine.generate_alert(event("a", risk_score=40, risk_level="medium"))
    assert engine.generate_alert(event("b", risk_score=40, risk_level="medium"))
    assert engine.generate_alert(event("a", risk_score=40, risk_level="medium")) is None
    assert engine.generate_alert(event("a", risk_score=80, risk_level="critical"))


def test_rate_limit_never_drops_a_critical_alert(tmp_path):
    engine = AlertEngine(snapshots_dir=str(tmp_path), max_alerts_per_minute=2)
    engine.notification_manager.notify_critical = Mock()
    for i in range(2):
        assert engine.generate_alert(event(event_id=f"m{i}", track_uuid=f"t{i}", risk_score=40, risk_level="medium"))
    # Busy camera: further routine alerts are rate limited...
    assert engine.generate_alert(event(event_id="m9", track_uuid="t9", risk_score=40, risk_level="medium")) is None
    # ...but a critical one (e.g. a wanted vehicle) still gets through, and counts.
    critical = event(event_id="w1", track_uuid="w1", event_type="watchlist_match", risk_score=90, risk_level="critical")
    assert engine.generate_alert(critical)
    assert len(engine._rate_counter["a"]) == 3


def test_alert_dedup_survives_tracker_id_churn(tmp_path):
    engine = AlertEngine(snapshots_dir=str(tmp_path))
    assert engine.generate_alert(event("a", track_id=1, risk_score=40, risk_level="medium"))
    assert engine.generate_alert(event("a", track_id=999, risk_score=40, risk_level="medium")) is None


def test_snapshot_capture_stops_at_storage_budget(tmp_path):
    engine = AlertEngine(snapshots_dir=str(tmp_path), max_snapshot_storage_mb=0)
    alert = engine.generate_alert(
        event("a", risk_score=40, risk_level="medium"),
        np.full((20, 20, 3), 255, dtype=np.uint8),
    )
    assert alert is not None
    assert alert.snapshot_path is None
    assert list(tmp_path.iterdir()) == []


def test_sqlite_foreign_keys_and_migrations_are_enabled(tmp_db):
    from sqlalchemy import text

    with tmp_db.engine.connect() as connection:
        assert connection.execute(text("PRAGMA foreign_keys")).scalar() == 1
        versions = {
            row[0] for row in connection.execute(text("SELECT version FROM schema_migrations"))
        }
    assert versions >= {1, 2}


def camera_pipeline(tmp_path, **kwargs):
    zones = ZoneManager()
    zones.add_zone(Zone("z", "restricted", "restricted", "a", [(0, 0), (100, 0), (100, 100), (0, 100)]))
    return CameraPipeline(CameraInfo("a", "A", "rtsp://camera", fps_limit=15), Mock(), zones,
                          FenceDetector(), {}, AlertEngine(snapshots_dir=str(tmp_path)), **kwargs)


@pytest.mark.parametrize("suppression", ["threshold", "cooldown", "rate"])
def test_event_persists_when_alert_is_suppressed(tmp_db, tmp_path, suppression):
    from src.database.models import AlertModel, EventModel
    from src.database.repository import Repository

    pipeline = camera_pipeline(tmp_path)
    engine = pipeline.alert_engine
    if suppression == "threshold":
        engine.min_risk_score = 101
    elif suppression == "rate":
        engine.max_alerts_per_minute = 0
    else:
        engine.generate_alert(event(risk_score=60, risk_level="high"))
    pipeline.night_detector.get_night_context = Mock(
        return_value={"is_night": False, "is_night_time": False, "brightness": 255}
    )
    with tmp_db.get_session() as session:
        Repository(session).create_camera("a", "A", "test")
    pipeline.evidence_buffer = Mock()
    track = Track(1, "person", "a", bbox=(20, 20, 40, 40))
    pipeline._process_track(track, np.full((100, 100, 3), 255, dtype=np.uint8))
    with tmp_db.get_session() as session:
        assert session.query(EventModel).count() == 1
        assert session.query(AlertModel).count() == 0
    # No alert -> no evidence clip (clips used to be cut for every event and filled the disk).
    pipeline.evidence_buffer.trigger.assert_not_called()


def test_alerting_incident_gets_an_evidence_clip(tmp_db, tmp_path):
    from src.database.repository import Repository

    pipeline = camera_pipeline(tmp_path)
    pipeline.evidence_buffer = Mock()
    pipeline.night_detector.get_night_context = Mock(
        return_value={"is_night": False, "is_night_time": False, "brightness": 255}
    )
    with tmp_db.get_session() as session:
        Repository(session).create_camera("a", "A", "test")
    pipeline._process_track(Track(1, "person", "a", bbox=(20, 20, 40, 40)), np.full((100, 100, 3), 255, np.uint8))
    pipeline.evidence_buffer.trigger.assert_called_once()


def test_publish_after_commit_and_rollback_on_failure(tmp_db, tmp_path, monkeypatch):
    from src.database.models import AlertModel, EventModel
    from src.database.repository import Repository

    pipeline = camera_pipeline(tmp_path)
    track = Track(1, "person", "a", bbox=(20, 20, 40, 40))
    with tmp_db.get_session() as session:
        Repository(session).create_camera("a", "A", "test")
    received = []

    def callback(alert):
        with tmp_db.get_session() as session:
            assert session.query(EventModel).filter_by(event_id=alert["event_id"]).one()
            assert session.query(AlertModel).filter_by(alert_id=alert["alert_id"]).one()
        received.append(alert)

    pipeline.alert_engine.register_callback(callback)
    frame = np.full((100, 100, 3), 255, dtype=np.uint8)
    original = Repository.create_alert
    monkeypatch.setattr(Repository, "create_alert", Mock(side_effect=RuntimeError("db failed")))
    with pytest.raises(RuntimeError):
        pipeline._process_track(track, frame)
    assert not received
    with tmp_db.get_session() as session:
        assert session.query(EventModel).count() == 0
    monkeypatch.setattr(Repository, "create_alert", original)
    pipeline._process_track(track, frame)
    assert len(received) == 1
    with tmp_db.get_session() as session:
        assert session.query(EventModel).one().evidence_hash


def test_zones_restore_and_deleted_defaults_stay_deleted(tmp_db):
    from src.database.repository import Repository

    config = {"zones": {"a": [{"id": "default", "name": "Default", "type": "restricted",
                                "points": [[0, 0], [100, 0], [0, 100]]}]}}
    pipeline = IBVAPPipeline()
    with tmp_db.get_session() as session:
        Repository(session).create_camera("a", "A", "test")
    pipeline._restore_zones(config)
    with tmp_db.get_session() as session:
        repo = Repository(session)
        repo.delete_zone("default")
        repo.create_zone({"zone_id": "saved", "camera_id": "a", "name": "Saved",
                          "points": [[0, 0], [100, 0], [0, 100]]})
    restarted = IBVAPPipeline()
    restarted._restore_zones(config)
    assert restarted.zone_manager.get_zone("default") is None
    assert restarted.zone_manager.is_in_restricted_zone("a", 10, 10)


def test_recovery_retries_initial_failure_and_stops(tmp_path):
    pipeline = camera_pipeline(tmp_path)
    source = pipeline.video_source
    source.connect = Mock(side_effect=[False, False, True])
    source.reconnect_delay = 0
    source.read_frame = Mock(side_effect=lambda: (setattr(pipeline, "_running", False), None))
    pipeline._running = True
    pipeline._process_loop()
    assert source.connect.call_count == 3
    pipeline._running = True
    pipeline._stop_event.set()
    assert not pipeline._recover_source()


def test_config_and_scoring_contracts(tmp_path):
    pipeline = camera_pipeline(tmp_path, thresholds={
        "tracking": {"max_age": 90, "min_hits": 4, "iou_threshold": 0.7},
        "behavior": {"loitering_threshold_seconds": 12, "night_start": "21:00",
                     "direction_min_points": 8, "low_light_brightness_threshold": 30},
    })
    assert pipeline.tracker.max_age == 90
    assert pipeline.tracker.min_hits == 4
    assert pipeline.loitering_detector.threshold_seconds == 12
    assert pipeline.night_detector.night_start.hour == 21
    assert pipeline.night_detector.brightness_threshold == 30
    risk = pipeline.risk_engine
    assert risk._calculate_identity_risk({"identity": "Alice", "identity_status": "uncertain"})[0] == 40
    assert risk._calculate_identity_risk({"identity": "unknown", "identity_status": "not_checked"})[0] == 0
    assert risk._calculate_vehicle_risk({"plate": "AB1234", "plate_status": "low_confidence"})[0] == 35


def test_loitering_clears_after_exit(tmp_path, monkeypatch):
    pipeline = camera_pipeline(tmp_path)
    detector = pipeline.loitering_detector
    track = Track(1, "person", "a")
    detector._zone_occupancy[(1, "z")] = time.time() - 60
    detector.check_loitering(track, ["z"])
    assert track.is_loitering
    detector.check_loitering(track, [])
    assert not track.is_loitering
    assert (1, "z") not in detector._flagged
