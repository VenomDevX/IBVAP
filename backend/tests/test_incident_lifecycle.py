"""Acceptance tests for track-aware incident semantics."""

from src.alerts.alert_engine import AlertEngine
from src.behavior.behavior_engine import BehaviorEngine
from src.features.anpr import PlateConsensus
from src.fusion.context_fusion import FusedEvent
from src.fusion.event_state_machine import EventStateMachine
from src.tracking.track import Track


def candidate(track, event_type="restricted_zone_entry", zone="z", level="high"):
    return FusedEvent(
        event_id="transient",
        camera_id=track.camera_id,
        track_id=track.track_id,
        track_uuid=track.track_uuid,
        timestamp=track.last_seen,
        object_type=track.object_type,
        event_type=event_type,
        risk_score=70,
        risk_level=level,
        zone_id=zone,
        spatial_context={"in_restricted": True, "zones": [zone]},
        temporal_context={"zone_session_id": track.zone_session_ids.get(zone, "visit-1")},
    )


def test_same_vehicle_in_zone_opens_exactly_one_incident():
    track = Track(1, "car", "cam", session_id="session-a")
    track.zone_session_ids["z"] = "visit-1"
    engine = EventStateMachine(confirmation_frames=3, confirmation_window=5, update_interval_seconds=0)
    transitions = []
    for second in range(20):
        track.last_seen = 1000 + second
        transitions.extend(engine.observe(track.track_uuid, [candidate(track)], track.last_seen))
    assert len([item for item in transitions if item.action == "opened"]) == 1
    assert len({item.event.event_id for item in transitions}) == 1
    assert engine.active_count == 1


def test_exit_and_reentry_after_cooldown_allows_second_event():
    track = Track(1, "person", "cam", session_id="session-a")
    track.zone_session_ids["z"] = "visit-1"
    engine = EventStateMachine(1, 1, exit_grace_seconds=1, cooldown_seconds=2)
    first = engine.observe(track.track_uuid, [candidate(track)], 100)[0].event.event_id
    engine.observe(track.track_uuid, [], 101)
    closed = engine.observe(track.track_uuid, [], 102)
    assert [item.action for item in closed] == ["closed"]
    track.zone_session_ids["z"] = "visit-2"
    second = engine.observe(track.track_uuid, [candidate(track)], 105)[0].event.event_id
    assert second != first


def test_tracker_id_reuse_in_new_session_is_not_same_track():
    assert Track(7, "car", "cam", session_id="a").track_uuid != Track(7, "car", "cam", session_id="b").track_uuid


def test_ten_observations_make_one_vehicle_profile(repo):
    repo.create_camera("cam", "Camera", "test")
    track = Track(8, "car", "cam", session_id="s")
    for offset in range(10):
        track.last_seen = track.first_seen + offset
        repo.upsert_vehicle_profile(track)
    from src.database.models import VehicleProfileModel

    assert repo.session.query(VehicleProfileModel).count() == 1


def test_plate_consensus_uses_repeated_measured_value():
    track = Track(2, "car", "cam")
    consensus = PlateConsensus(min_observations=3, min_confidence=0.5)
    observations = ["HR26AB1234", "HR26A81234", "HR26AB1234", "HR26AB1234"]
    result = ("UNKNOWN", 0.0)
    for value in observations:
        result = consensus.add(track, value, 0.9)
    assert result[0] == "HR26AB1234"


def test_night_movement_is_context_only_by_default():
    track = Track(1, "car", "cam")
    track.trajectory = [(0, 0, 1), (20, 0, 2)]
    events = BehaviorEngine().analyze_track(
        track,
        {"in_restricted": False},
        {"is_night": True},
        {"toward_restricted": False},
        {"crossed": False, "approaching": False},
    )
    assert events == []


def test_one_alert_per_event_id(tmp_path):
    engine = AlertEngine(cooldown_seconds=0, snapshots_dir=str(tmp_path))
    track = Track(1, "car", "cam")
    event = candidate(track)
    event.event_id = "one-incident"
    assert engine.generate_alert(event) is not None
    assert engine.generate_alert(event) is None


def test_resolved_or_closed_incident_leaves_active_count(repo):
    repo.create_camera("cam", "Camera", "test")
    track = Track(3, "person", "cam")
    incident = candidate(track)
    incident.event_id = "event-active"
    incident.state = "OPEN"
    incident.opened_at = incident.timestamp
    incident.last_updated = incident.timestamp
    repo.create_event(incident.to_dict())
    repo.create_alert(
        {
            "alert_id": "alert-active",
            "event_id": incident.event_id,
            "camera_id": "cam",
            "timestamp": incident.timestamp,
            "event_type": incident.event_type,
            "risk_level": "high",
        }
    )
    assert repo.get_dashboard_stats()["unreviewed_alerts"] == 1
    repo.update_alert_workflow("alert-active", "operator", status="acknowledged")
    assert repo.get_dashboard_stats()["unreviewed_alerts"] == 1
    repo.update_alert_workflow("alert-active", "operator", status="resolved")
    assert repo.get_dashboard_stats()["unreviewed_alerts"] == 0


def test_false_positive_feedback_is_structured(repo):
    repo.create_camera("cam", "Camera", "test")
    track = Track(4, "car", "cam")
    incident = candidate(track)
    incident.event_id = "event-feedback"
    incident.state = "OPEN"
    repo.create_event(incident.to_dict())
    alert = repo.create_alert(
        {
            "alert_id": "alert-feedback",
            "event_id": incident.event_id,
            "camera_id": "cam",
            "timestamp": incident.timestamp,
            "event_type": incident.event_type,
        }
    )
    repo.update_alert_workflow(alert.alert_id, "operator", status="false_positive")
    feedback = repo.create_operator_feedback(alert, "operator", "Duplicate alert")
    repo.session.commit()
    assert feedback.reason == "Duplicate alert"
    assert feedback.event_id == incident.event_id
