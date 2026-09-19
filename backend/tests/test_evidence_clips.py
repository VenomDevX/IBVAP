"""Evidence clip budgets: clips must never fill the disk."""

import time
from collections import namedtuple

import numpy as np

from src.alerts import evidence_clip
from src.alerts.evidence_clip import EvidenceClipBuffer

Usage = namedtuple("Usage", "total used free")


def _buffer(tmp_path, **kwargs):
    return EvidenceClipBuffer("cam", tmp_path, pre_seconds=0.2, post_seconds=0.0, capture_fps=50, **kwargs)


def _drain(buffer, n=3):
    """Feed frames so pending clips complete, then wait for the writer pool."""
    for _ in range(n):
        buffer.add_frame(np.zeros((32, 32, 3), np.uint8), timestamp=time.time())
        time.sleep(0.03)
    EvidenceClipBuffer._writers.submit(lambda: None).result(5)


def test_hourly_clip_budget(tmp_path):
    buffer = _buffer(tmp_path, max_clips_per_hour=2)
    _drain(buffer, 1)
    assert buffer.trigger("E1") and buffer.trigger("E2")
    assert not buffer.trigger("E3")
    _drain(buffer)
    assert len(list(tmp_path.glob("*.avi"))) == 2


def test_clip_storage_budget(tmp_path):
    # Clips already on disk at startup count against the budget.
    (tmp_path / "old.avi").write_bytes(b"x" * (2 * 1024 * 1024))
    buffer = _buffer(tmp_path, max_storage_mb=1)
    assert not buffer.trigger("E1")


def test_clip_budget_is_shared_between_cameras(tmp_path):
    # 1 KB budget: the first clip is allowed (nothing written yet), any clip
    # written by camera "a" must then block camera "b" in the same directory.
    a = _buffer(tmp_path, max_storage_mb=0.001)
    b = EvidenceClipBuffer("b", tmp_path, pre_seconds=0.2, post_seconds=0.0, capture_fps=50, max_storage_mb=0.001)
    _drain(a, 1)
    assert a.trigger("E1")
    _drain(a)
    assert list(tmp_path.glob("cam_E1.avi"))
    assert not b.trigger("E2")


def test_free_disk_reserve(tmp_path, monkeypatch):
    buffer = _buffer(tmp_path, min_free_mb=1024)
    monkeypatch.setattr(evidence_clip.shutil, "disk_usage", lambda _p: Usage(10, 10, 100 * 1024 * 1024))
    assert not buffer.trigger("E1")


def _purge_module():
    import importlib
    import os
    import sys

    scripts = os.path.join(os.path.dirname(__file__), "..", "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    return importlib.import_module("purge_expired")


def test_purge_removes_expired_and_orphaned_clips(repo, tmp_path):
    import os
    from datetime import datetime

    from src.database.models import EventEvidenceModel

    purge = _purge_module()
    repo.create_camera(camera_id="c1", name="C1", stream_url="x")
    for eid in ("OLD", "NEW"):
        repo.create_event({"event_id": eid, "camera_id": "c1", "event_type": "t", "timestamp": time.time()})
        repo.create_event_evidence(eid, "pre_post_clip", clip_path=str(tmp_path / f"c1_{eid}.avi"))
    for name in ("c1_OLD.avi", "c1_NEW.avi", "c1_ORPHAN.avi"):
        (tmp_path / name).write_bytes(b"clip")
    old = time.time() - 40 * 86400
    os.utime(tmp_path / "c1_OLD.avi", (old, old))

    # Dry run reports but keeps everything.
    assert purge.purge_clips(repo.session, str(tmp_path), 30, datetime.utcnow(), dry_run=True)["files"] == 2
    assert len(list(tmp_path.glob("*.avi"))) == 3

    assert purge.purge_clips(repo.session, str(tmp_path), 30, datetime.utcnow(), dry_run=False)["files"] == 2
    assert sorted(p.name for p in tmp_path.glob("*.avi")) == ["c1_NEW.avi"]
    remaining = repo.session.query(EventEvidenceModel).filter(EventEvidenceModel.clip_path.isnot(None)).all()
    assert [os.path.basename(r.clip_path) for r in remaining] == ["c1_NEW.avi"]
