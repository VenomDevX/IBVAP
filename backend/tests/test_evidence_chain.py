"""Evidence hash chain: verification and chain-safe retention purges."""

import time
from datetime import datetime, timedelta

import pytest

from src.alerts.evidence_chain import purge_chained_prefix, verify_table
from src.database.models import AlertModel, EventEvidenceModel, EventModel, EvidenceCheckpointModel

DAY = 86400


@pytest.fixture(autouse=True)
def _stable_key(monkeypatch):
    monkeypatch.setenv("EVIDENCE_HMAC_KEY", "test-key-for-evidence-chain")


def _seed(repo, ages_days, with_alerts=True):
    repo.create_camera(camera_id="c1", name="C1", stream_url="x")
    now = time.time()
    for i, age in enumerate(ages_days):
        ts = now - age * DAY
        repo.create_event({"event_id": f"E{i}", "camera_id": "c1", "event_type": "t", "timestamp": ts,
                           "risk_score": 10.0, "risk_level": "low"})
        repo.create_event_evidence(f"E{i}", "snapshot", snapshot_path=f"s{i}.jpg")
        if with_alerts:
            repo.create_alert({"alert_id": f"A{i}", "camera_id": "c1", "event_id": f"E{i}",
                               "event_type": "t", "timestamp": ts, "risk_score": 50.0})


def _cutoff(days):
    return datetime.utcnow() - timedelta(days=days)


def test_intact_chain_verifies(repo):
    _seed(repo, [5, 4, 3])
    for table in ("events", "alerts"):
        report = verify_table(repo.session, table)
        assert report.ok and report.rows == 3


def test_purge_keeps_chain_verifiable(repo):
    _seed(repo, [200, 190, 10, 5])
    assert purge_chained_prefix(repo.session, "alerts", _cutoff(180)) == 2
    assert purge_chained_prefix(repo.session, "events", _cutoff(180)) == 2

    assert [e.event_id for e in repo.session.query(EventModel).order_by(EventModel.id)] == ["E2", "E3"]
    assert repo.session.query(EventEvidenceModel).count() == 2
    assert repo.session.query(EvidenceCheckpointModel).count() == 2
    for table in ("events", "alerts"):
        assert verify_table(repo.session, table).ok, table


def test_unrecorded_head_deletion_is_detected(repo):
    _seed(repo, [5, 4, 3], with_alerts=False)
    repo.session.query(EventEvidenceModel).filter_by(event_id="E0").delete()
    repo.session.query(EventModel).filter_by(event_id="E0").delete()
    repo.session.commit()
    report = verify_table(repo.session, "events")
    assert not report.ok
    assert "head truncated" in report.breaks[0]


def test_deleting_past_a_checkpoint_is_detected(repo):
    _seed(repo, [200, 5, 4], with_alerts=False)
    purge_chained_prefix(repo.session, "events", _cutoff(180))
    assert verify_table(repo.session, "events").ok
    # An attacker removes one more row and hopes the checkpoint covers it.
    repo.session.query(EventEvidenceModel).filter_by(event_id="E1").delete()
    repo.session.query(EventModel).filter_by(event_id="E1").delete()
    repo.session.commit()
    assert not verify_table(repo.session, "events").ok


def test_forged_checkpoint_is_ignored(repo):
    _seed(repo, [5, 4], with_alerts=False)
    head_hash = repo.session.query(EventModel).filter_by(event_id="E0").one().chain_hash
    repo.session.query(EventEvidenceModel).filter_by(event_id="E0").delete()
    repo.session.query(EventModel).filter_by(event_id="E0").delete()
    repo.session.add(EvidenceCheckpointModel(table_name="events", anchor_hash=head_hash,
                                             rows_purged=1, created_at=datetime.utcnow(), mac="0" * 64))
    repo.session.commit()
    assert not verify_table(repo.session, "events").ok


def test_purge_only_removes_a_prefix(repo):
    # An old row after a newer one must survive, or the chain would get a hole.
    _seed(repo, [200, 5, 200], with_alerts=False)
    assert purge_chained_prefix(repo.session, "events", _cutoff(180)) == 1
    assert [e.event_id for e in repo.session.query(EventModel).order_by(EventModel.id)] == ["E1", "E2"]
    assert verify_table(repo.session, "events").ok


def test_events_referenced_by_surviving_alerts_are_kept(repo):
    _seed(repo, [200, 5])
    # Alert retention is longer than event retention here: nothing is purged from alerts.
    assert purge_chained_prefix(repo.session, "alerts", _cutoff(365)) == 0
    assert purge_chained_prefix(repo.session, "events", _cutoff(180)) == 0
    assert repo.session.query(AlertModel).count() == 2


def test_dry_run_deletes_nothing(repo):
    _seed(repo, [200, 5], with_alerts=False)
    assert purge_chained_prefix(repo.session, "events", _cutoff(180), dry_run=True) == 1
    assert repo.session.query(EventModel).count() == 2
    assert repo.session.query(EvidenceCheckpointModel).count() == 0
