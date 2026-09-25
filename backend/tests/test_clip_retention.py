"""Deleting old evidence clips: shared logic, API, and the live recording budget."""

import os
import time
from datetime import datetime

import pytest

from src.alerts.clip_retention import clip_usage, purge_clips
from src.alerts.evidence_clip import EvidenceClipBuffer
from src.database.models import EventEvidenceModel

DAY = 86400


@pytest.fixture
def clips(repo, tmp_path):
    """Two alert-less events: one clip 40 days old, one new; plus an orphan file."""
    repo.create_camera(camera_id="c1", name="C1", stream_url="x")
    for eid, age in (("OLD", 40), ("NEW", 1)):
        repo.create_event({"event_id": eid, "camera_id": "c1", "event_type": "t", "timestamp": time.time()})
        path = tmp_path / f"c1_{eid}.avi"
        path.write_bytes(b"x" * 1000)
        stamp = time.time() - age * DAY
        os.utime(path, (stamp, stamp))
        repo.create_event_evidence(eid, "pre_post_clip", clip_path=str(path))
    (tmp_path / "c1_ORPHAN.avi").write_bytes(b"x" * 500)
    return tmp_path


def test_usage_counts_clip_files(clips):
    assert clip_usage(str(clips)) == {"files": 3, "bytes": 2500}


def test_older_than_removes_old_and_orphans(repo, clips):
    preview = purge_clips(repo.session, str(clips), 30, datetime.utcnow(), dry_run=True)
    assert preview == {"files": 2, "bytes": 1500}
    assert len(list(clips.glob("*.avi"))) == 3

    done = purge_clips(repo.session, str(clips), 30, datetime.utcnow(), dry_run=False)
    assert done == preview
    assert [p.name for p in clips.glob("*.avi")] == ["c1_NEW.avi"]
    rows = repo.session.query(EventEvidenceModel).filter(EventEvidenceModel.clip_path.isnot(None)).all()
    assert [os.path.basename(r.clip_path) for r in rows] == ["c1_NEW.avi"]


def test_purge_refreshes_the_live_recording_budget(repo, clips):
    buffer = EvidenceClipBuffer("c1", clips, max_storage_mb=0.002)  # 2 KB; 2.5 KB on disk
    assert not buffer.trigger("E1")
    purge_clips(repo.session, str(clips), 30, datetime.utcnow(), dry_run=False)
    assert buffer.trigger("E1")  # 1 KB left: recording resumes without a restart


def _client_user(monkeypatch, role):
    from tests.conftest import make_token

    return {"Authorization": make_token(role, monkeypatch)}


def test_api_storage_and_purge(client, monkeypatch, tmp_path):
    import src.api.routes.storage as storage_routes
    from src.database.db import get_database
    from src.database.models import AuditLogModel
    from src.database.repository import Repository

    monkeypatch.setattr(storage_routes, "clip_dir", lambda: str(tmp_path))
    with get_database().get_session() as session:
        repo = Repository(session)
        repo.create_camera(camera_id="c1", name="C1", stream_url="x")
        repo.create_event({"event_id": "OLD", "camera_id": "c1", "event_type": "t", "timestamp": time.time()})
        path = tmp_path / "c1_OLD.avi"
        path.write_bytes(b"x" * 2048)
        old = time.time() - 60 * DAY
        os.utime(path, (old, old))
        repo.create_event_evidence("OLD", "pre_post_clip", clip_path=str(path))

    operator = _client_user(monkeypatch, "operator")
    usage = client.get("/api/storage/clips", headers=operator)
    assert usage.status_code == 200
    assert usage.json()["files"] == 1
    assert client.post("/api/storage/clips/purge", headers=operator, json={"older_than_days": 30}).status_code == 403

    admin = _client_user(monkeypatch, "admin")
    assert client.post("/api/storage/clips/purge", headers=admin, json={"older_than_days": 0}).status_code == 422
    preview = client.post("/api/storage/clips/purge", headers=admin, json={"older_than_days": 30, "dry_run": True})
    assert preview.json() == {"files": 1, "freed_mb": 0.0, "freed_bytes": 2048, "dry_run": True}
    assert path.exists()

    done = client.post("/api/storage/clips/purge", headers=admin, json={"older_than_days": 30})
    assert done.status_code == 200 and done.json()["files"] == 1
    assert not path.exists()
    with get_database().get_session() as session:
        logs = session.query(AuditLogModel).filter_by(action="purge_clips").all()
    assert len(logs) == 1 and logs[0].details["older_than_days"] == 30
