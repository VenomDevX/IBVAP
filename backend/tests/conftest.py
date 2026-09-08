"""Shared test fixtures. Run: pip install -r requirements-dev.txt && pytest"""
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

os.environ.setdefault("IBVAP_ENV", "development")
os.environ.setdefault("EVIDENCE_HMAC_KEY", "test-hmac-key")
os.environ.pop("SUPABASE_JWT_SECRET", None)
os.environ.pop("SUPABASE_SERVICE_KEY", None)


@pytest.fixture()
def tmp_db(monkeypatch):
    path = tempfile.mktemp(suffix=".db")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{path}")
    import src.database.db as dbmod
    monkeypatch.setattr(dbmod, "_db_instance", None)
    db = dbmod.get_database()
    yield db
    db.close()


@pytest.fixture()
def repo(tmp_db):
    from src.database.repository import Repository
    s = tmp_db.get_session()
    yield Repository(s)
    s.close()


@pytest.fixture()
def client(monkeypatch, tmp_db):
    """TestClient with a no-op lifespan and a monkeypatched token verifier."""
    import contextlib
    import src.api.app as appmod

    @contextlib.asynccontextmanager
    async def _noop(app):
        yield

    monkeypatch.setattr(appmod, "lifespan", _noop)

    from fastapi.testclient import TestClient
    app = appmod.create_app()
    app.router.lifespan_context = _noop
    with TestClient(app, base_url="http://localhost", raise_server_exceptions=False) as c:
        yield c


def make_token(role="operator", monkeypatch=None):
    """A fake auth: monkeypatch _verify_token + resolve_profile to return this identity."""
    import src.api.auth as auth
    payload = {"sub": f"user-{role}", "email": f"{role}@ibvap.local"}
    if monkeypatch:
        monkeypatch.setattr(auth, "_verify_token", lambda t: payload)
        monkeypatch.setattr(auth, "resolve_profile",
                            lambda uid: {"role": role, "allowed_areas": []})
    return "Bearer faketoken"
