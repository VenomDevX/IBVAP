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


def test_escalation_does_not_break_the_chain(repo):
    _seed(repo, [1, 1])
    repo.update_event_lifecycle({"event_id": "E0", "risk_score": 90.0, "risk_level": "critical", "state": "CLOSED"})
    repo.update_alert_from_event({"event_id": "E0", "risk_score": 90.0, "risk_level": "critical"})
    for table in ("events", "alerts"):
        assert verify_table(repo.session, table).ok, table


def test_legacy_v1_rows_still_verify(repo):
    from src.alerts import evidence
    from src.alerts.evidence_chain import fields_for

    _seed(repo, [1], with_alerts=False)
    row = repo.session.query(EventModel).one()
    # Re-hash the row the way the v1 code did (risk included, no version).
    row.chain_version = None
    row.chain_hash = evidence.compute_hash({f: getattr(row, f) for f in fields_for("events", 1)}, None)
    from src.database.models import EvidenceChainHeadModel
    repo.session.query(EvidenceChainHeadModel).filter_by(table_name="events").update({"head_hash": row.chain_hash})
    repo.session.commit()
    assert verify_table(repo.session, "events").ok
    row.risk_score = 1.0  # v1 rows DO cover risk
    repo.session.commit()
    assert not verify_table(repo.session, "events").ok


def test_tail_truncation_is_detected(repo):
    _seed(repo, [3, 2, 1], with_alerts=False)
    repo.session.query(EventEvidenceModel).filter_by(event_id="E2").delete()
    repo.session.query(EventModel).filter_by(event_id="E2").delete()
    repo.session.commit()
    report = verify_table(repo.session, "events")
    assert any("tail truncated" in b for b in report.breaks)


def test_concurrent_writers_do_not_fork_the_chain(tmp_db):
    """Two sessions (as two backend processes would) append at the same time."""
    import threading

    from src.database.repository import Repository

    with tmp_db.get_session() as s:
        Repository(s).create_camera(camera_id="c1", name="C1", stream_url="x")

    first = tmp_db.get_session()
    Repository(first).create_event({"event_id": "EA", "camera_id": "c1", "event_type": "t",
                                    "timestamp": time.time()}, commit=False)
    # `first` now holds the write lock with an uncommitted append.
    done = threading.Event()

    def second_writer():
        with tmp_db.get_session() as s:
            Repository(s).create_event({"event_id": "EB", "camera_id": "c1", "event_type": "t",
                                        "timestamp": time.time()})
        done.set()

    t = threading.Thread(target=second_writer)
    t.start()
    assert not done.wait(0.5), "second writer must wait for the first transaction"
    first.commit()
    first.close()
    t.join(10)
    assert done.is_set()

    with tmp_db.get_session() as s:
        rows = s.query(EventModel).order_by(EventModel.id).all()
        assert [r.event_id for r in rows] == ["EA", "EB"]
        assert rows[1].prev_hash == rows[0].chain_hash
        assert verify_table(s, "events").ok


def test_append_links_to_rows_written_by_older_code(repo):
    """An old-version process appends without touching the head row."""
    from src.alerts import evidence
    from src.alerts.evidence_chain import fields_for

    _seed(repo, [1], with_alerts=False)
    legacy = EventModel(event_id="LEGACY", camera_id="c1", event_type="t", timestamp=datetime.utcnow(),
                        object_type="", risk_score=0.0, risk_level="low")
    last = repo.session.query(EventModel).one()
    legacy.prev_hash = last.chain_hash
    legacy.chain_hash = evidence.compute_hash({f: getattr(legacy, f) for f in fields_for("events", 1)},
                                              last.chain_hash)
    repo.session.add(legacy)
    repo.session.commit()

    repo.create_event({"event_id": "NEW", "camera_id": "c1", "event_type": "t", "timestamp": time.time()})
    new = repo.session.query(EventModel).filter_by(event_id="NEW").one()
    assert new.prev_hash == legacy.chain_hash
    assert verify_table(repo.session, "events").ok


def test_rows_appended_during_verification_are_not_reported(repo, monkeypatch):
    from sqlalchemy.orm import Query

    import src.alerts.evidence_chain as ec

    _seed(repo, [2, 1], with_alerts=False)
    real_iter = Query.__iter__
    state = {"appended": False}

    def iter_then_append(self):
        reading_events = self.column_descriptions and self.column_descriptions[0].get("entity") is EventModel
        yield from real_iter(self)
        # A live writer appends right AFTER the verifier has read all the rows.
        if reading_events and not state["appended"]:
            state["appended"] = True
            repo.create_event({"event_id": "LIVE", "camera_id": "c1", "event_type": "t",
                               "timestamp": time.time()})

    monkeypatch.setattr(Query, "__iter__", iter_then_append)
    assert ec.verify_table(repo.session, "events").ok
    assert state["appended"]
