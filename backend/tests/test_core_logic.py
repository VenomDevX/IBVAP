"""Risk engine scoring, evidence chain, and bounded-collection regression."""

import time

import yaml


def _risk_cfg():
    import os

    p = os.path.join(os.path.dirname(__file__), "..", "configs", "risk_weights.yaml")
    return yaml.safe_load(open(p, encoding="utf-8"))


def _fused(object_type="person", **ctx):
    from src.fusion.context_fusion import FusedEvent

    return FusedEvent(
        event_id="e",
        camera_id="c",
        track_id=1,
        timestamp=time.time(),
        object_type=object_type,
        event_type=ctx.get("event_type", "restricted_zone_entry"),
        spatial_context=ctx.get("spatial", {}),
        temporal_context=ctx.get("temporal", {}),
        identity_context=ctx.get("identity", {}),
        vehicle_context=ctx.get("vehicle", {}),
    )


def test_risk_restricted_zone_person_is_medium_plus():
    from src.risk.risk_engine import RiskEngine

    e = RiskEngine(_risk_cfg())
    score, level, reasons = e.calculate_risk(_fused("person", spatial={"in_restricted": True}))
    assert score > 0
    assert level in ("medium", "high", "critical")
    assert any("restricted" in r.lower() for r in reasons)


def test_risk_military_object_scores_above_person():
    from src.risk.risk_engine import RiskEngine

    e = RiskEngine(_risk_cfg())
    person, *_ = e.calculate_risk(_fused("person", spatial={"in_restricted": True}))
    tank, _, reasons = e.calculate_risk(_fused("military_ground_vehicle", spatial={"in_restricted": True}))
    assert tank >= person
    assert any("object class" in r.lower() for r in reasons)


def test_risk_is_deterministic():
    from src.risk.risk_engine import RiskEngine

    e = RiskEngine(_risk_cfg())
    fe = _fused("person", spatial={"in_restricted": True}, temporal={"is_night": True})
    a = e.calculate_risk(fe)
    b = e.calculate_risk(_fused("person", spatial={"in_restricted": True}, temporal={"is_night": True}))
    assert a == b


def test_evidence_chain_detects_tampering(repo):
    from src.alerts import evidence
    from src.database.models import AlertModel

    repo.create_camera(camera_id="c1", name="C1", stream_url="x")
    for i in range(5):
        repo.create_event(
            {
                "event_id": f"E{i}",
                "camera_id": "c1",
                "event_type": "t",
                "timestamp": time.time(),
                "risk_score": 10.0,
                "risk_level": "low",
            }
        )
        repo.create_alert(
            {
                "alert_id": f"A{i}",
                "camera_id": "c1",
                "event_id": f"E{i}",
                "event_type": "t",
                "timestamp": time.time(),
                "risk_score": 50.0,
            }
        )

    fields = [
        "alert_id",
        "camera_id",
        "event_id",
        "track_id",
        "event_type",
        "timestamp",
        "risk_score",
        "risk_level",
        "object_type",
        "snapshot_hash",
    ]
    rows = repo.session.query(AlertModel).order_by(AlertModel.id).all()
    prev = None
    for row in rows:
        rec = {f: getattr(row, f) for f in fields}
        assert evidence.verify(rec, prev, row.chain_hash)
        prev = row.chain_hash

    rows[2].risk_score = 9999.0
    repo.session.commit()
    prev, broke = None, None
    for row in repo.session.query(AlertModel).order_by(AlertModel.id).all():
        rec = {f: getattr(row, f) for f in fields}
        if not evidence.verify(rec, prev, row.chain_hash) and broke is None:
            broke = row.alert_id
        prev = row.chain_hash
    assert broke == "A2"


def test_collections_stay_bounded():
    import collections

    from src.alerts.alert_engine import AlertEngine
    from src.behavior.behavior_engine import BehaviorEngine
    from src.detection.detector import ObjectDetector
    from src.fusion.context_fusion import ContextFusion

    ae = AlertEngine()
    assert isinstance(ae._alerts, collections.deque) and ae._alerts.maxlen
    assert isinstance(ContextFusion()._fused_events, collections.deque)
    assert isinstance(BehaviorEngine()._recent_events, collections.deque)
    d = ObjectDetector.__new__(ObjectDetector)
    d.__init__.__wrapped__ if False else None
    # _inference_times is a bounded deque
    od = ObjectDetector(model_path="nonexistent.pt")
    assert isinstance(od._inference_times, collections.deque)
    assert od._inference_times.maxlen == 200
