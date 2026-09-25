"""A camera a user enabled/disabled stays that way across a backend restart,
and every camera change is recorded in the audit log with old and new values."""

from src.database.models import AuditLogModel, CameraModel
from src.database.repository import Repository
from src.pipeline.pipeline import IBVAPPipeline
from tests.conftest import make_token

YAML = {
    "cameras": [
        {"id": "cam_a", "name": "A", "source": "./data/demo/a.mp4", "fps": 10, "enabled": True},
        {"id": "cam_b", "name": "B", "source": "./data/demo/b.mp4", "fps": 10, "enabled": False},
    ]
}


def _startup(tmp_db):
    """What IBVAPPipeline.initialize does with cameras: sync YAML, pick cameras to run."""
    pipeline = IBVAPPipeline()
    pipeline._sync_cameras(YAML)
    with tmp_db.get_session() as session:
        return {c.camera_id for c in pipeline._cameras_to_start(session)}


def _row(tmp_db, camera_id):
    with tmp_db.get_session() as session:
        row = session.query(CameraModel).filter_by(camera_id=camera_id).one()
        session.expunge(row)
        return row


def test_yaml_seeds_new_cameras(tmp_db):
    assert _startup(tmp_db) == {"cam_a"}
    assert _row(tmp_db, "cam_b").enabled is False


def test_user_toggle_survives_restart(tmp_db):
    _startup(tmp_db)
    with tmp_db.get_session() as session:
        repo = Repository(session)
        repo.update_camera("cam_a", {"enabled": False}, by_user=True)
        repo.update_camera("cam_b", {"enabled": True, "fps_limit": 5}, by_user=True)

    assert _startup(tmp_db) == {"cam_b"}  # restart
    assert _row(tmp_db, "cam_a").enabled is False
    assert _row(tmp_db, "cam_b").fps_limit == 5
    assert sorted(_row(tmp_db, "cam_b").user_overrides) == ["enabled", "fps_limit"]


def test_yaml_still_updates_fields_the_user_never_touched(tmp_db):
    _startup(tmp_db)
    with tmp_db.get_session() as session:
        Repository(session).update_camera("cam_a", {"enabled": False}, by_user=True)
    renamed = {"cameras": [dict(YAML["cameras"][0], name="A renamed", enabled=True), YAML["cameras"][1]]}
    pipeline = IBVAPPipeline()
    pipeline._sync_cameras(renamed)
    row = _row(tmp_db, "cam_a")
    assert row.name == "A renamed"
    assert row.enabled is False


def test_retired_camera_stays_retired(tmp_db):
    _startup(tmp_db)
    with tmp_db.get_session() as session:
        Repository(session).retire_camera("cam_a")
    assert _startup(tmp_db) == set()
    assert _row(tmp_db, "cam_a").status == "retired"


def test_camera_added_in_the_ui_starts_after_restart(tmp_db):
    _startup(tmp_db)
    with tmp_db.get_session() as session:
        Repository(session).create_camera("ui_cam", "UI camera", "rtsp://10.0.0.5/stream", enabled=True)
    assert _startup(tmp_db) == {"cam_a", "ui_cam"}


def _audit(tmp_db, action):
    with tmp_db.get_session() as session:
        return [(a.username, a.details) for a in session.query(AuditLogModel).filter_by(action=action)]


def test_toggle_is_audited_as_enable_or_disable(client, monkeypatch, tmp_db):
    with tmp_db.get_session() as session:
        Repository(session).create_camera("cam_x", "X", "rtsp://user:secret@10.0.0.9/live")
    headers = {"Authorization": make_token("admin", monkeypatch)}

    assert client.patch("/api/cameras/cam_x", headers=headers, json={"enabled": False}).status_code == 200
    assert client.patch("/api/cameras/cam_x", headers=headers, json={"enabled": True}).status_code == 200
    assert [d["camera_id"] for _, d in _audit(tmp_db, "disable_camera")] == ["cam_x"]
    assert [d["camera_id"] for _, d in _audit(tmp_db, "enable_camera")] == ["cam_x"]
    assert _audit(tmp_db, "disable_camera")[0][0] == "admin@ibvap.local"
    assert _row(tmp_db, "cam_x").user_overrides == ["enabled"]


def test_saving_an_unchanged_form_does_not_freeze_fields(tmp_db):
    _startup(tmp_db)
    with tmp_db.get_session() as session:
        Repository(session).update_camera("cam_a", {"name": "A", "fps_limit": 10, "enabled": False}, by_user=True)
    assert _row(tmp_db, "cam_a").user_overrides == ["enabled"]


def test_edit_is_audited_with_old_and_new_values_and_no_secrets(client, monkeypatch, tmp_db):
    with tmp_db.get_session() as session:
        Repository(session).create_camera("cam_y", "Y", "rtsp://user:secret@10.0.0.9/live", fps_limit=15)
    headers = {"Authorization": make_token("admin", monkeypatch)}
    response = client.patch(
        "/api/cameras/cam_y",
        headers=headers,
        json={
            "name": "Gate Y",
            "fps_limit": 8,
            "source": "rtsp://user:newsecret@10.0.0.10/live",
        },
    )
    assert response.status_code == 200
    ((_, details),) = _audit(tmp_db, "update_camera")
    changes = details["changes"]
    assert changes["name"] == {"from": "Y", "to": "Gate Y"}
    assert changes["fps_limit"] == {"from": 15, "to": 8}
    assert "secret" not in str(changes["source"])
    assert changes["source"]["to"] == "rtsp://***@10.0.0.10/live"


def test_media_ticket_requests_are_not_audited(client, monkeypatch, tmp_db):
    headers = {"Authorization": make_token("admin", monkeypatch)}
    client.post("/api/auth/media-ticket", headers=headers)
    with tmp_db.get_session() as session:
        assert session.query(AuditLogModel).filter(AuditLogModel.action.like("%media-ticket%")).count() == 0


def test_audit_api_can_hide_raw_requests(client, monkeypatch, tmp_db):
    with tmp_db.get_session() as session:
        repo = Repository(session)
        repo.create_audit_log("PATCH /api/cameras/cam_x", "admin@ibvap.local", {"status": 200})
        repo.create_audit_log("disable_camera", "admin@ibvap.local", {"camera_id": "cam_x"})
    headers = {"Authorization": make_token("admin", monkeypatch)}
    everything = {row["action"] for row in client.get("/api/audit", headers=headers).json()}
    actions = {row["action"] for row in client.get("/api/audit?actions_only=true", headers=headers).json()}
    assert {"PATCH /api/cameras/cam_x", "disable_camera"} <= everything
    assert "disable_camera" in actions and not any(" /" in a for a in actions)
    assert all(row["timestamp"].endswith("Z") for row in client.get("/api/audit", headers=headers).json())


def test_zone_disable_is_audited(client, monkeypatch, tmp_db):
    with tmp_db.get_session() as session:
        repo = Repository(session)
        repo.create_camera("cam_z", "Z", "rtsp://10.0.0.2/live")
        repo.create_zone({"zone_id": "z1", "camera_id": "cam_z", "name": "Gate", "points": [[0, 0], [10, 0], [0, 10]]})
    headers = {"Authorization": make_token("admin", monkeypatch)}
    assert client.patch("/api/zones/z1", headers=headers, json={"enabled": False}).status_code == 200
    assert client.patch("/api/zones/z1", headers=headers, json={"name": "Gate 2"}).status_code == 200
    assert [d["zone_id"] for _, d in _audit(tmp_db, "disable_zone")] == ["z1"]
    assert _audit(tmp_db, "update_zone")[0][1]["changes"] == {"name": {"from": "Gate", "to": "Gate 2"}}
