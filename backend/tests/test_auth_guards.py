"""Every route requires auth; admin routes require the admin role; JWT hardening."""

import pytest

from tests.conftest import make_token

UNAUTH_401 = [
    ("GET", "/api/cameras"),
    ("GET", "/api/events"),
    ("GET", "/api/alerts"),
    ("GET", "/api/zones"),
    ("GET", "/api/tracks"),
    ("GET", "/api/statistics"),
    ("GET", "/api/audit"),
    ("GET", "/api/reports/daily"),
    ("GET", "/snapshots/anything.jpg"),
    ("POST", "/api/alerts/x/review"),
]


@pytest.mark.parametrize("method,path", UNAUTH_401)
def test_requires_auth(client, method, path):
    r = client.request(method, path)
    assert r.status_code in (401, 403), f"{method} {path} -> {r.status_code}"


def test_health_is_open(client):
    assert client.get("/api/health").status_code == 200


def test_snapshot_path_traversal_blocked(client):
    for p in ("/snapshots/..%2f..%2fetc%2fpasswd", "/snapshots/....//x.jpg"):
        assert client.get(p).status_code in (400, 401, 403, 404)


def test_admin_route_rejects_operator(client, monkeypatch):
    make_token("operator", monkeypatch)
    r = client.request("DELETE", "/api/zones/z1", headers={"Authorization": "Bearer x"})
    assert r.status_code == 403


def test_admin_route_allows_admin(client, monkeypatch):
    make_token("admin", monkeypatch)
    r = client.request("DELETE", "/api/zones/z1", headers={"Authorization": "Bearer x"})
    # 404 (no such zone) is fine — the point is it got past the guard
    assert r.status_code in (200, 404)


def test_audit_route_rejects_operator(client, monkeypatch):
    make_token("operator", monkeypatch)
    r = client.get("/api/audit", headers={"Authorization": "Bearer x"})
    assert r.status_code == 403


def test_jwt_rejects_alg_none_and_bad_sig(monkeypatch):
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "s3cret")
    import importlib

    import src.api.auth as auth

    importlib.reload(auth)
    import jwt as pyjwt
    from fastapi import HTTPException

    none_tok = pyjwt.encode({"sub": "x", "aud": "authenticated"}, key="", algorithm="none")
    with pytest.raises(HTTPException):
        auth._verify_token(none_tok)

    bad = pyjwt.encode({"sub": "x", "aud": "authenticated"}, "wrong", algorithm="HS256")
    with pytest.raises(HTTPException):
        auth._verify_token(bad)
    importlib.reload(auth)


def test_jwt_requires_second_factor(monkeypatch):
    """A password-only (aal1) token is refused; the same token after the TOTP step (aal2) passes."""
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "s3cret")
    import importlib

    import src.api.auth as auth

    importlib.reload(auth)
    import jwt as pyjwt
    from fastapi import HTTPException

    required = {"role": "operator", "allowed_areas": [], "mfa_required": True}
    monkeypatch.setattr(auth, "resolve_profile", lambda uid: required)
    claims = {"sub": "x", "aud": "authenticated", "exp": 9999999999}
    aal1 = pyjwt.encode({**claims, "aal": "aal1"}, "s3cret", algorithm="HS256")
    with pytest.raises(HTTPException) as err:
        auth._verify_token(aal1)
    assert err.value.detail == "mfa_required"

    aal2 = pyjwt.encode({**claims, "aal": "aal2"}, "s3cret", algorithm="HS256")
    assert auth._verify_token(aal2)["sub"] == "x"

    # An admin exempted this user: the password-only token is accepted.
    monkeypatch.setattr(auth, "resolve_profile", lambda uid: {**required, "mfa_required": False})
    assert auth._verify_token(aal1)["sub"] == "x"
    importlib.reload(auth)


def test_reset_mfa_is_admin_only(client, monkeypatch):
    make_token("operator", monkeypatch)
    r = client.post(
        "/api/auth/users/00000000-0000-0000-0000-000000000000/reset-mfa", headers={"Authorization": "Bearer x"}
    )
    assert r.status_code == 403


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/api/auth/users"),
        ("PUT", "/api/auth/users/00000000-0000-0000-0000-000000000000/mfa"),
    ],
)
def test_user_mfa_admin_routes_reject_operator(client, monkeypatch, method, path):
    make_token("operator", monkeypatch)
    r = client.request(method, path, json={"required": False}, headers={"Authorization": "Bearer x"})
    assert r.status_code == 403
