"""Regression tests for the 2026-09-09 hardening pass.

Covers: input-validation false positives, camera-id sanitisation, heatmap bounds,
WebSocket auth (subprotocol + query fallback + expiry), proxy-aware client IP,
notifier redaction, and the seed-script password policy.
"""

import time

import pytest
from starlette.testclient import WebSocketDenialResponse, WebSocketDisconnect

from tests.conftest import make_token

WS_REJECT = (WebSocketDisconnect, WebSocketDenialResponse)


# --------------------------------------------------------------------------- #
# InputValidationMiddleware — no longer trips on ordinary params
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "qs",
    [
        "online=true",
        "section=events&sort=on",
        "reasonable=1&limit=50",
    ],
)
def test_benign_query_not_blocked(client, qs):
    # 401 (needs auth) is fine — the point is it's NOT a 400 from the validator
    r = client.get(f"/api/events?{qs}")
    assert r.status_code != 400, f"benign query wrongly blocked: {qs}"


@pytest.mark.parametrize(
    "qs",
    [
        "q=<script>alert(1)</script>",
        "x=javascript:evil()",
        "x=<img src=x onerror=alert(1)>",
        "path=/etc/passwd",
    ],
)
def test_injection_query_blocked(client, qs):
    r = client.get(f"/api/events?{qs}")
    assert r.status_code == 400


def test_path_traversal_blocked(client):
    assert client.get("/snapshots/..%2f..%2fetc%2fpasswd").status_code in (400, 404)


# --------------------------------------------------------------------------- #
# camera-id sanitisation
# --------------------------------------------------------------------------- #


def test_sanitize_camera_id_strips_dangerous_chars():
    from src.api.middleware.input_validator import sanitize_camera_id

    assert sanitize_camera_id("CAM_1") == "CAM_1"
    assert sanitize_camera_id("../../etc/passwd") == "etcpasswd"
    assert sanitize_camera_id("a b;rm -rf/") == "abrm-rf"
    assert sanitize_camera_id("") == ""


# --------------------------------------------------------------------------- #
# heatmap window bounds
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("window", [0, 5, 3601, 99999, -1])
def test_heatmap_window_out_of_range_rejected(client, monkeypatch, window):
    make_token("operator", monkeypatch)
    r = client.get(f"/api/cameras/CAM_X/heatmap?window={window}", headers={"Authorization": "Bearer x"})
    assert r.status_code == 422


# --------------------------------------------------------------------------- #
# proxy-aware client IP
# --------------------------------------------------------------------------- #


def test_client_ip_ignores_xff_without_trusted_proxy(monkeypatch):
    import importlib

    monkeypatch.delenv("TRUSTED_PROXY", raising=False)
    import src.api.net as net

    importlib.reload(net)

    class _Req:
        client = type("C", (), {"host": "10.0.0.1"})()
        headers = {"x-forwarded-for": "1.2.3.4"}

    assert net.client_ip(_Req()) == "10.0.0.1"
    importlib.reload(net)


def test_client_ip_uses_xff_first_hop_when_trusted(monkeypatch):
    import importlib

    monkeypatch.setenv("TRUSTED_PROXY", "1")
    import src.api.net as net

    importlib.reload(net)

    class _Req:
        client = type("C", (), {"host": "10.0.0.1"})()
        headers = {"x-forwarded-for": "1.2.3.4, 10.0.0.1"}

    assert net.client_ip(_Req()) == "1.2.3.4"
    importlib.reload(net)


# --------------------------------------------------------------------------- #
# WebSocket auth
# --------------------------------------------------------------------------- #


def _raise(*_a, **_k):
    raise ValueError("bad token")


def test_ws_rejects_missing_token(client):
    with pytest.raises(WS_REJECT):
        with client.websocket_connect("/ws/alerts"):
            pass


def test_ws_rejects_bad_token(client, monkeypatch):
    import src.api.auth as auth

    monkeypatch.setattr(auth, "_verify_token", _raise)
    with pytest.raises(WS_REJECT):
        with client.websocket_connect("/ws/alerts?token=nope"):
            pass


def test_ws_accepts_subprotocol_token(client, monkeypatch):
    import src.api.auth as auth

    monkeypatch.setattr(auth, "_verify_token", lambda t: {"sub": "u1", "exp": time.time() + 3600})
    # authenticate_ws also calls resolve_profile(sub); without a real Supabase
    # client "u1" is not "dev-admin" so it raises "Profile service unavailable",
    # which authenticate_ws's except swallows into a 4003 close - the socket
    # never got as far as testing the subprotocol-token path this test is for.
    monkeypatch.setattr(auth, "resolve_profile", lambda uid: {"role": "operator", "allowed_areas": []})
    from src.api.websocket import ws_manager

    with client.websocket_connect("/ws/alerts", subprotocols=["bearer", "tok"]):
        assert ws_manager.connection_count == 1
    assert ws_manager.connection_count == 0


def test_ws_token_expired_is_flagged():
    from src.api.websocket import WebSocketManager

    mgr = WebSocketManager()
    s = object()
    mgr._identities[id(s)] = {"exp": time.time() - 10}
    assert mgr.token_expired(s) is True
    mgr._identities[id(s)] = {"exp": time.time() + 10}
    assert mgr.token_expired(s) is False


# --------------------------------------------------------------------------- #
# notifier redaction
# --------------------------------------------------------------------------- #


def test_notifier_redaction():
    from src.alerts.notifiers import _redact_email, _redact_phone

    assert _redact_email("operator@ibvap.gov") == "o***@ibvap.gov"
    assert _redact_email("") == "<unset>"
    assert _redact_phone("+1 (555) 123-4567") == "***4567"
    assert _redact_phone("12") == "<unset>"


# --------------------------------------------------------------------------- #
# seed-script password policy
# --------------------------------------------------------------------------- #


def test_seed_generates_password_when_env_unset(monkeypatch):
    import importlib
    import sys

    sys.path.insert(0, "scripts")
    seed = importlib.import_module("seed_users")

    # module import runs load_dotenv() — clear the var *after* that
    monkeypatch.delenv("IBVAP_ADMIN_PASSWORD", raising=False)
    pw, generated = seed._password("IBVAP_ADMIN_PASSWORD")
    assert generated is True
    assert len(pw) >= 16 and pw != "admin123"

    monkeypatch.setenv("IBVAP_ADMIN_PASSWORD", "s3t-by-operator")
    pw2, gen2 = seed._password("IBVAP_ADMIN_PASSWORD")
    assert (pw2, gen2) == ("s3t-by-operator", False)


# --------------------------------------------------------------------------- #
# Server-side logout / token revocation (2026-09-09 batch)
# --------------------------------------------------------------------------- #


def test_logout_revokes_the_token(client, monkeypatch, tmp_db):
    import src.api.auth as auth
    import src.api.token_revocation as tr

    monkeypatch.setattr(
        auth, "_verify_token", lambda t: {"sub": "user-x", "email": "x@ibvap.local", "exp": time.time() + 3600}
    )
    monkeypatch.setattr(auth, "resolve_profile", lambda uid: {"role": "operator", "allowed_areas": []})
    tr._loaded = False
    tr._revoked.clear()

    h = {"Authorization": "Bearer tok-abc"}
    assert client.get("/api/cameras", headers=h).status_code == 200
    assert client.post("/api/auth/logout", headers=h).status_code == 200
    assert client.get("/api/cameras", headers=h).status_code == 401
    assert tr.is_token_revoked("tok-abc") is True


def test_revocation_helper_roundtrip(tmp_db):
    import src.api.token_revocation as tr

    tr._loaded = False
    tr._revoked.clear()
    assert tr.is_token_revoked("never") is False
    tr.revoke_token("bye", time.time() + 60)
    assert tr.is_token_revoked("bye") is True


# --------------------------------------------------------------------------- #
# Body-level injection scanning
# --------------------------------------------------------------------------- #


def test_injection_in_json_body_blocked(client):
    r = client.post(
        "/api/zones/anything",
        headers={"Content-Type": "application/json"},
        content='{"name": "<script>alert(1)</script>"}',
    )
    assert r.status_code == 400


def test_clean_json_body_passes_validator(client, monkeypatch):
    make_token("admin", monkeypatch)
    r = client.request(
        "DELETE",
        "/api/zones/z1",
        headers={"Authorization": "Bearer x", "Content-Type": "application/json"},
        content='{"reason": "cleanup, no markup here"}',
    )
    assert r.status_code != 400


# --------------------------------------------------------------------------- #
# Production startup assertions
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("bad", ["SUPABASE_JWT_SECRET", "SUPABASE_SERVICE_KEY", "EVIDENCE_HMAC_KEY"])
def test_production_refuses_to_start_without_required_secrets(monkeypatch, bad):
    import src.api.app as appmod

    monkeypatch.setenv("IBVAP_ENV", "production")
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "real-secret")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "real-service-key")
    monkeypatch.setenv("EVIDENCE_HMAC_KEY", "a-real-strong-key")
    if bad == "EVIDENCE_HMAC_KEY":
        monkeypatch.setenv("EVIDENCE_HMAC_KEY", "change-me")
    else:
        monkeypatch.delenv(bad, raising=False)
    with pytest.raises(RuntimeError):
        appmod._assert_production_config()


# ──────────────────────────────────────────────────────────────
# scoped_cameras() must fail closed, not open.
#
# allowed_areas defaults to [] for a newly created profile (see
# models.py: allowed_areas = Column(JSON, default=list)). An earlier version
# of scoped_cameras() treated that empty list the same as "unrestricted",
# which meant a brand-new operator or auditor account - before an admin ever
# assigned it a camera - could see every camera in the system. Only "admin"
# may get unrestricted (None); every other role gets exactly its own list,
# empty or not.
# ──────────────────────────────────────────────────────────────


def test_scoped_cameras_admin_is_unrestricted():
    from src.api.auth import scoped_cameras

    assert scoped_cameras({"app_role": "admin", "allowed_areas": []}) is None
    assert scoped_cameras({"app_role": "admin", "allowed_areas": None}) is None


def test_scoped_cameras_empty_allowed_areas_means_zero_cameras():
    """THE regression this guards against: [] must stay [], never become None."""
    from src.api.auth import scoped_cameras

    for role in ("operator", "auditor"):
        result = scoped_cameras({"app_role": role, "allowed_areas": []})
        assert result == [], (
            f"{role} with allowed_areas=[] must see ZERO cameras, got {result!r} "
            "(None here would mean unrestricted access)"
        )


def test_scoped_cameras_returns_exact_list_for_non_admin():
    from src.api.auth import scoped_cameras

    assert scoped_cameras({"app_role": "operator", "allowed_areas": ["cam1", "cam2"]}) == [
        "cam1",
        "cam2",
    ]


def test_scoped_cameras_invalid_role_or_shape_denies_all():
    from src.api.auth import scoped_cameras

    assert scoped_cameras({"app_role": "not-a-real-role", "allowed_areas": ["cam1"]}) == []
    assert scoped_cameras({"app_role": "operator", "allowed_areas": "not-a-list"}) == []
    assert scoped_cameras({}) == []


def test_can_access_camera_denies_when_scope_is_empty():
    from src.api.auth import can_access_camera

    user = {"app_role": "operator", "allowed_areas": []}
    assert can_access_camera(user, "CAM_1") is False


def test_can_access_camera_admin_sees_everything():
    from src.api.auth import can_access_camera

    admin = {"app_role": "admin", "allowed_areas": []}
    assert can_access_camera(admin, "CAM_ANYTHING") is True
