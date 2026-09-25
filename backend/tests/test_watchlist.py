"""Face / plate watchlists: storage, encryption, matching."""

import numpy as np
import pytest

from src.watchlist import crypto
from src.watchlist.service import WatchlistService, canonical_plate, normalize_plate


@pytest.fixture(autouse=True)
def _keys(monkeypatch):
    monkeypatch.delenv("WATCHLIST_ENCRYPTION_KEY", raising=False)
    monkeypatch.setenv("EVIDENCE_HMAC_KEY", "test-hmac-key-for-watchlists")


def _unit(*values):
    v = np.asarray(values, np.float32)
    return v / np.linalg.norm(v)


# --------------------------------------------------------------------------- #
# Plates
# --------------------------------------------------------------------------- #


def test_plate_normalisation():
    assert normalize_plate(" mh-12 ab 3456 ") == "MH12AB3456"
    assert normalize_plate("") == ""
    # OCR confusions collapse to the same canonical form.
    assert canonical_plate("MH12AB3456") == canonical_plate("MH12A83456") == canonical_plate("MHI2AB3456")


def test_plate_match_exact_and_ocr_tolerant(repo):
    repo.create_watchlist_entry(
        kind="plate", list_type="wanted", label="Stolen truck", plate="MH 12 AB 3456", created_by="admin"
    )
    service = WatchlistService()
    service.load(repo.session)

    exact = service.match_plate("MH12AB3456")
    assert exact is not None and exact.exact and exact.list_type == "wanted" and exact.label == "Stolen truck"

    fuzzy = service.match_plate("MH12A83456")  # B read as 8
    assert fuzzy is not None and not fuzzy.exact

    assert service.match_plate("KA05MN9999") is None
    assert service.match_plate("") is None


def test_exact_match_beats_fuzzy_match(repo):
    repo.create_watchlist_entry(
        kind="plate", list_type="authorized", label="Patrol jeep", plate="DL01AB1234", created_by="admin"
    )
    repo.create_watchlist_entry(
        kind="plate", list_type="wanted", label="Look-alike", plate="DL01A81234", created_by="admin"
    )
    service = WatchlistService()
    service.load(repo.session)
    assert service.match_plate("DL01AB1234").label == "Patrol jeep"


def test_deactivated_entries_do_not_match(repo):
    entry = repo.create_watchlist_entry(
        kind="plate", list_type="wanted", label="x", plate="UP32XY0001", created_by="admin"
    )
    assert repo.deactivate_watchlist_entry(entry.entry_id, actor="admin")
    service = WatchlistService()
    service.load(repo.session)
    assert service.match_plate("UP32XY0001") is None
    assert not repo.deactivate_watchlist_entry(entry.entry_id, actor="admin")  # already inactive


def test_duplicate_active_plate_is_rejected(repo):
    repo.create_watchlist_entry(kind="plate", list_type="wanted", label="a", plate="HR26DK8337", created_by="admin")
    with pytest.raises(ValueError):
        repo.create_watchlist_entry(kind="plate", list_type="vip", label="b", plate="hr-26 dk 8337", created_by="admin")


# --------------------------------------------------------------------------- #
# Faces
# --------------------------------------------------------------------------- #


def test_face_embeddings_are_encrypted_at_rest(repo):
    embedding = _unit(0.1, 0.2, 0.3, 0.4)
    entry = repo.create_watchlist_entry(
        kind="face", list_type="wanted", label="Suspect A", embedding=embedding, created_by="admin"
    )
    stored = entry.embedding_enc
    assert stored and "0.1" not in stored
    assert np.allclose(crypto.decrypt_embedding(stored), embedding)


def test_face_match_uses_threshold(repo):
    repo.create_watchlist_entry(
        kind="face", list_type="wanted", label="Suspect A", embedding=_unit(1, 0, 0), created_by="admin"
    )
    repo.create_watchlist_entry(
        kind="face", list_type="authorized", label="Guard B", embedding=_unit(0, 1, 0), created_by="admin"
    )
    service = WatchlistService(face_threshold=0.5)
    service.load(repo.session)

    hit = service.match_face(_unit(0.95, 0.1, 0))
    assert hit.label == "Suspect A" and hit.list_type == "wanted" and hit.score > 0.9
    assert service.match_face(_unit(0.1, 0.95, 0)).label == "Guard B"
    assert service.match_face(_unit(0, 0, 1)) is None
    assert service.match_face(None) is None


def test_undecryptable_face_entries_are_skipped(repo, monkeypatch):
    repo.create_watchlist_entry(kind="face", list_type="wanted", label="A", embedding=_unit(1, 0), created_by="x")
    monkeypatch.setenv("EVIDENCE_HMAC_KEY", "a-different-key")
    service = WatchlistService()
    service.load(repo.session)  # must not raise
    assert service.match_face(_unit(1, 0)) is None
    assert service.skipped_entries == 1


def test_explicit_encryption_key_is_used(monkeypatch):
    from cryptography.fernet import Fernet

    monkeypatch.setenv("WATCHLIST_ENCRYPTION_KEY", Fernet.generate_key().decode())
    token = crypto.encrypt_embedding(_unit(1, 2))
    monkeypatch.setenv("WATCHLIST_ENCRYPTION_KEY", Fernet.generate_key().decode())
    with pytest.raises(crypto.WatchlistKeyError):
        crypto.decrypt_embedding(token)


def test_missing_keys_refuse_to_encrypt(monkeypatch):
    monkeypatch.delenv("EVIDENCE_HMAC_KEY", raising=False)
    with pytest.raises(crypto.WatchlistKeyError):
        crypto.encrypt_embedding(_unit(1, 0))


def test_service_reload_picks_up_changes(repo):
    service = WatchlistService()
    service.load(repo.session)
    assert service.match_plate("TN09BC4321") is None
    version = service.version
    repo.create_watchlist_entry(kind="plate", list_type="wanted", label="n", plate="TN09BC4321", created_by="a")
    service.load(repo.session)
    assert service.match_plate("TN09BC4321") is not None
    assert service.version == version + 1


# --------------------------------------------------------------------------- #
# Risk, behaviour and pipeline integration
# --------------------------------------------------------------------------- #


def _risk_engine():
    import os

    import yaml

    from src.risk.risk_engine import RiskEngine

    path = os.path.join(os.path.dirname(__file__), "..", "configs", "risk_weights.yaml")
    with open(path, encoding="utf-8") as fh:
        return RiskEngine(yaml.safe_load(fh))


def _fused(event_type="general_activity", object_type="person", identity=None, vehicle=None):
    import time

    from src.fusion.context_fusion import FusedEvent

    return FusedEvent(
        event_id="e",
        camera_id="c",
        track_id=1,
        timestamp=time.time(),
        object_type=object_type,
        event_type=event_type,
        identity_context=identity or {},
        vehicle_context=vehicle or {},
    )


WANTED_FACE = {
    "entry_id": "WL_1",
    "kind": "face",
    "list_type": "wanted",
    "label": "Suspect A",
    "score": 0.8,
    "exact": True,
}


def test_wanted_match_is_always_critical():
    engine = _risk_engine()
    scored = engine.score_fused_event(_fused(identity={"identity_status": "wanted", "watchlist": WANTED_FACE}))
    assert scored.risk_level == "critical"
    assert any("Suspect A" in reason for reason in scored.contributing_factors)


def test_wanted_plate_is_critical_and_authorized_face_adds_no_risk():
    engine = _risk_engine()
    plate_hit = {**WANTED_FACE, "kind": "plate", "label": "Stolen truck"}
    scored = engine.score_fused_event(
        _fused(object_type="truck", vehicle={"plate_status": "read", "watchlist": plate_hit})
    )
    assert scored.risk_level == "critical"

    authorized = {**WANTED_FACE, "list_type": "authorized", "label": "Guard B"}
    known = engine.score_fused_event(_fused(identity={"identity_status": "known", "watchlist": authorized}))
    unknown = engine.score_fused_event(_fused(identity={"identity_status": "unknown"}))
    assert known.score_breakdown["identity"]["raw_score"] == 0
    assert known.risk_score < unknown.risk_score


def test_wanted_track_raises_watchlist_event_without_other_behaviour():
    from src.behavior.behavior_engine import BehaviorEngine, BehaviorType
    from src.fusion.context_fusion import ContextFusion
    from src.tracking.track import Track

    track = Track(1, "person", "c")
    engine = BehaviorEngine()
    assert engine.analyze_track(track, {}, {}, {}, {}, apply_cooldown=False) == []

    track.watchlist = dict(WANTED_FACE)
    events = engine.analyze_track(track, {}, {}, {}, {}, apply_cooldown=False)
    assert [e.behavior_type for e in events] == [BehaviorType.WATCHLIST_MATCH]
    fused = ContextFusion().fuse_events(1, "c", "person", events, {}, {}, identity_context={})
    assert fused.event_type == "watchlist_match"


def test_pipeline_applies_plate_hit(repo, tmp_path, monkeypatch):
    from unittest.mock import Mock

    from src.alerts.alert_engine import AlertEngine
    from src.ingestion.video_source import CameraInfo
    from src.pipeline import pipeline as pipeline_mod
    from src.pipeline.pipeline import CameraPipeline
    from src.spatial.fence_detector import FenceDetector
    from src.spatial.zone_manager import ZoneManager
    from src.tracking.track import Track
    from src.watchlist.service import WatchlistService

    repo.create_watchlist_entry(
        kind="plate", list_type="wanted", label="Stolen truck", plate="MH12AB3456", created_by="admin"
    )
    service = WatchlistService()
    service.load(repo.session)
    monkeypatch.setattr(pipeline_mod, "get_watchlist", lambda: service)
    monkeypatch.setattr(pipeline_mod, "extract_plate", lambda crop, **_: {"text": "MH12AB3456", "confidence": 0.9})

    cam = CameraPipeline(
        CameraInfo("c", "C", "rtsp://x"),
        Mock(),
        ZoneManager(),
        FenceDetector(),
        {},
        AlertEngine(snapshots_dir=str(tmp_path)),
    )
    cam.plate_consensus.min_observations = 1
    track = Track(1, "truck", "c")
    track.best_frame = np.zeros((10, 10, 3), np.uint8)
    cam._run_anpr_check(track)
    assert track.license_plate == "MH12AB3456"
    assert track.watchlist["list_type"] == "wanted"
    assert track.watchlist_status == "wanted"


def test_wanted_hit_is_not_downgraded_by_a_later_authorized_hit():
    from src.pipeline.pipeline import apply_watchlist_hit
    from src.tracking.track import Track
    from src.watchlist.service import WatchlistHit

    track = Track(1, "person", "c")
    apply_watchlist_hit(track, WatchlistHit("WL_1", "face", "wanted", "Suspect A"))
    apply_watchlist_hit(track, WatchlistHit("WL_2", "plate", "authorized", "Patrol"))
    assert track.watchlist["entry_id"] == "WL_1"
    apply_watchlist_hit(track, None)
    assert track.watchlist_status == "wanted"


def test_pipeline_face_hit_marks_track_wanted(repo, tmp_path, monkeypatch):
    from unittest.mock import Mock

    from src.alerts.alert_engine import AlertEngine
    from src.ingestion.video_source import CameraInfo
    from src.pipeline import pipeline as pipeline_mod
    from src.pipeline.pipeline import CameraPipeline
    from src.spatial.fence_detector import FenceDetector
    from src.spatial.zone_manager import ZoneManager
    from src.tracking.track import Track
    from src.watchlist.service import WatchlistService

    repo.create_camera(camera_id="c", name="C", stream_url="x")
    repo.create_watchlist_entry(
        kind="face", list_type="wanted", label="Suspect A", embedding=_unit(1, 0, 0), created_by="admin"
    )
    service = WatchlistService(face_threshold=0.5)
    service.load(repo.session)
    monkeypatch.setattr(pipeline_mod, "get_watchlist", lambda: service)

    recognizer = Mock()
    recognizer.best_face.return_value = {"embedding": list(_unit(0.98, 0.05, 0)), "confidence": 0.9}
    cam = CameraPipeline(
        CameraInfo("c", "C", "rtsp://x"),
        Mock(),
        ZoneManager(),
        FenceDetector(),
        {},
        AlertEngine(snapshots_dir=str(tmp_path)),
        face_recognizer=recognizer,
    )
    track = Track(1, "person", "c")
    track.best_frame = np.zeros((10, 10, 3), np.uint8)
    cam._run_face_identify(track)
    assert track.identity_status == "wanted"
    assert track.identity_label == "Suspect A"
    recognizer.match.assert_not_called()  # the gallery is irrelevant once a watchlist hit is found

    from src.database.models import IdentityResultModel

    assert repo.session.query(IdentityResultModel).one().identity_label == "Suspect A"


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #


def _png(width=64, height=64):
    import cv2

    ok, buf = cv2.imencode(".png", np.full((height, width, 3), 127, np.uint8))
    assert ok
    return buf.tobytes()


def test_api_plate_lifecycle_and_roles(client, monkeypatch):
    from tests.conftest import make_token

    headers = {"Authorization": make_token("viewer", monkeypatch)}
    assert client.get("/api/watchlists", headers=headers).status_code == 403

    headers = {"Authorization": make_token("operator", monkeypatch)}
    assert client.get("/api/watchlists", headers=headers).status_code == 200
    assert (
        client.post("/api/watchlists/plates", headers=headers, json={"plate": "MH12AB3456", "label": "x"}).status_code
        == 403
    )

    headers = {"Authorization": make_token("commander", monkeypatch)}
    # The security middleware (400) or the schema (422) must stop script-like input.
    bad = client.post("/api/watchlists/plates", headers=headers, json={"plate": "<script>", "label": "x"})
    assert bad.status_code in (400, 422)
    short = client.post("/api/watchlists/plates", headers=headers, json={"plate": "AB", "label": "x"})
    assert short.status_code == 422
    created = client.post(
        "/api/watchlists/plates",
        headers=headers,
        json={"plate": "mh-12 ab 3456", "label": "Stolen truck", "list_type": "wanted"},
    )
    assert created.status_code == 201, created.text
    entry = created.json()
    assert entry["plate"] == "MH12AB3456" and "embedding_enc" not in entry

    dup = client.post("/api/watchlists/plates", headers=headers, json={"plate": "MH12AB3456", "label": "y"})
    assert dup.status_code == 409

    from src.watchlist.service import get_watchlist

    assert get_watchlist().match_plate("MH12AB3456") is not None

    listing = client.get("/api/watchlists?kind=plate", headers=headers).json()
    assert [e["entry_id"] for e in listing["entries"]] == [entry["entry_id"]]

    assert client.delete(f"/api/watchlists/{entry['entry_id']}", headers=headers).status_code == 200
    assert client.delete(f"/api/watchlists/{entry['entry_id']}", headers=headers).status_code == 404
    assert get_watchlist().match_plate("MH12AB3456") is None
    assert client.get("/api/watchlists", headers=headers).json()["entries"] == []

    from src.database.db import get_database
    from src.database.models import AuditLogModel

    with get_database().get_session() as session:
        actions = [a.action for a in session.query(AuditLogModel).filter(AuditLogModel.action.like("watchlist%"))]
    assert actions == ["watchlist_add", "watchlist_remove"]


def test_api_face_enrolment(client, monkeypatch):
    from types import SimpleNamespace

    import src.api.app as appmod
    from tests.conftest import make_token

    headers = {"Authorization": make_token("supervisor", monkeypatch)}
    form = {"label": "Suspect A", "list_type": "wanted"}
    files = {"image": ("face.png", _png(), "image/png")}

    monkeypatch.setattr(appmod, "get_pipeline", lambda: None)
    assert client.post("/api/watchlists/faces", headers=headers, data=form, files=files).status_code == 503

    faces = []
    recognizer = SimpleNamespace(active=True, faces=lambda image: list(faces))
    monkeypatch.setattr(appmod, "get_pipeline", lambda: SimpleNamespace(face_recognizer=recognizer))

    assert client.post("/api/watchlists/faces", headers=headers, data=form, files=files).status_code == 422
    faces[:] = [{"embedding": [1.0, 0.0]}, {"embedding": [0.0, 1.0]}]
    assert client.post("/api/watchlists/faces", headers=headers, data=form, files=files).status_code == 422

    not_image = {"image": ("face.png", b"not an image at all", "image/png")}
    assert client.post("/api/watchlists/faces", headers=headers, data=form, files=not_image).status_code == 400

    faces[:] = [{"embedding": list(_unit(1, 0, 0))}]
    created = client.post("/api/watchlists/faces", headers=headers, data=form, files=files)
    assert created.status_code == 201, created.text
    assert created.json()["kind"] == "face"

    from src.watchlist.service import get_watchlist

    assert get_watchlist().match_face(_unit(1, 0, 0)).label == "Suspect A"


# --------------------------------------------------------------------------- #
# Fuzzy matching must not merge distinct real registrations
# --------------------------------------------------------------------------- #


def test_fuzzy_never_matches_an_allow_list_entry(repo):
    """Confusable folding helps a deny-list; on an allow-list it is fail-open."""
    repo.create_watchlist_entry(
        kind="plate", list_type="authorized", label="Patrol jeep", plate="DL01OB1234", created_by="admin"
    )
    service = WatchlistService()
    service.load(repo.session)

    assert service.match_plate("DL01OB1234").exact  # exact still works
    assert service.match_plate("DL01QB1234") is None  # lookalike gets no free pass


def test_ambiguous_canonical_key_matches_nothing(repo):
    """OD/DD and IB/LB are distinct valid registrations that fold together."""
    repo.create_watchlist_entry(
        kind="plate", list_type="wanted", label="Odisha car", plate="OD12AB1234", created_by="admin"
    )
    repo.create_watchlist_entry(
        kind="plate", list_type="wanted", label="Daman car", plate="DD12AB1234", created_by="admin"
    )
    service = WatchlistService()
    service.load(repo.session)

    # Each still matches itself exactly.
    assert service.match_plate("OD12AB1234").label == "Odisha car"
    assert service.match_plate("DD12AB1234").label == "Daman car"
    # A read that folds onto both must not silently pick whichever was enrolled first.
    assert service.match_plate("QD12AB1234") is None


def test_fuzzy_wanted_hit_is_marked_inexact(repo):
    repo.create_watchlist_entry(
        kind="plate", list_type="wanted", label="Stolen truck", plate="MH12AB3456", created_by="admin"
    )
    service = WatchlistService()
    service.load(repo.session)

    fuzzy = service.match_plate("MH12A83456")  # B read as 8
    assert fuzzy is not None and not fuzzy.exact and fuzzy.list_type == "wanted"


# --------------------------------------------------------------------------- #
# An inexact (confusable-folded) hit must not be treated as a confirmed one
# --------------------------------------------------------------------------- #

INEXACT_WANTED_PLATE = {
    "entry_id": "WL_9",
    "kind": "plate",
    "list_type": "wanted",
    "label": "Stolen truck",
    "score": 0.9,
    "exact": False,
}


def test_inexact_wanted_hit_is_not_forced_critical():
    """A fuzzy plate collision must be a review item, not an automatic critical."""
    engine = _risk_engine()
    scored = engine.score_fused_event(
        _fused(object_type="truck", vehicle={"plate_status": "read", "watchlist": INEXACT_WANTED_PLATE})
    )
    assert scored.risk_level != "critical"
    assert any("possible" in reason.lower() for reason in scored.contributing_factors)

    exact = {**INEXACT_WANTED_PLATE, "exact": True}
    confirmed = engine.score_fused_event(
        _fused(object_type="truck", vehicle={"plate_status": "read", "watchlist": exact})
    )
    assert confirmed.risk_level == "critical"


def test_inexact_wanted_hit_raises_no_watchlist_behaviour_event():
    from src.behavior.behavior_engine import BehaviorEngine, BehaviorType
    from src.tracking.track import Track

    track = Track(1, "car", "c")
    track.watchlist = dict(INEXACT_WANTED_PLATE)
    events = BehaviorEngine().analyze_track(track, {}, {}, {}, {}, apply_cooldown=False)
    assert not any(e.behavior_type == BehaviorType.WATCHLIST_MATCH for e in events)

    track2 = Track(2, "car", "c")
    track2.watchlist = {**INEXACT_WANTED_PLATE, "exact": True}
    events2 = BehaviorEngine().analyze_track(track2, {}, {}, {}, {}, apply_cooldown=False)
    assert any(e.behavior_type == BehaviorType.WATCHLIST_MATCH for e in events2)


def test_a_confirmed_read_replaces_an_inexact_hit_of_the_same_list():
    from src.pipeline.pipeline import apply_watchlist_hit
    from src.tracking.track import Track
    from src.watchlist.service import WatchlistHit

    track = Track(1, "car", "c")
    apply_watchlist_hit(track, WatchlistHit("WL_9", "plate", "wanted", "Stolen truck", 0.9, exact=False))
    assert track.watchlist["exact"] is False
    # A later exact read of the same list must be able to confirm (not be latched out).
    apply_watchlist_hit(track, WatchlistHit("WL_9", "plate", "wanted", "Stolen truck", 1.0, exact=True))
    assert track.watchlist["exact"] is True
