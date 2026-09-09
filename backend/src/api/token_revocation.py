"""
Server-side token revocation (logout that actually logs out).

Supabase access tokens live ~1 h; without this, "log out" only clears the
browser and the JWT stays valid until it expires. On logout the API records a
SHA-256 of the token; every authenticated request then checks it.

Storage: a `revoked_tokens` SQLite row per revoked token (survives restarts) plus
an in-process set so the hot path is a membership test, not a DB hit. Expired
rows are swept lazily. Single-process uvicorn is assumed; a multi-worker
deployment would need the set refreshed from the DB periodically.
"""

import hashlib
import time
from datetime import UTC, datetime

from loguru import logger

_revoked: set[str] = set()
_loaded = False
_last_sweep = 0.0
_SWEEP_EVERY = 300  # seconds


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _load() -> None:
    """Populate the in-memory set from the DB once, on first use."""
    global _loaded
    if _loaded:
        return
    try:
        from src.database.db import get_database
        from src.database.models import RevokedTokenModel

        now = datetime.now(UTC)
        s = get_database().get_session()
        try:
            rows = s.query(RevokedTokenModel.token_hash).filter(RevokedTokenModel.expires_at > now).all()
            _revoked.update(h for (h,) in rows)
        finally:
            s.close()
    except Exception as e:  # noqa: BLE001 — never let this break auth
        logger.error(f"token_revocation: load failed: {e}")
    _loaded = True


def _sweep() -> None:
    global _last_sweep
    now = time.time()
    if now - _last_sweep < _SWEEP_EVERY:
        return
    _last_sweep = now
    try:
        from src.database.db import get_database
        from src.database.models import RevokedTokenModel

        cutoff = datetime.now(UTC)
        s = get_database().get_session()
        try:
            expired = s.query(RevokedTokenModel).filter(RevokedTokenModel.expires_at <= cutoff).all()
            for row in expired:
                _revoked.discard(row.token_hash)
                s.delete(row)
            if expired:
                s.commit()
        finally:
            s.close()
    except Exception as e:  # noqa: BLE001
        logger.error(f"token_revocation: sweep failed: {e}")


def revoke_token(token: str, exp_ts: float | None) -> None:
    """Add a token to the denylist until its own `exp` (or +1 h if unknown)."""
    _load()
    h = _hash(token)
    _revoked.add(h)
    expires = datetime.fromtimestamp(exp_ts or (time.time() + 3600), tz=UTC)
    try:
        from src.database.db import get_database
        from src.database.models import RevokedTokenModel

        s = get_database().get_session()
        try:
            if not s.query(RevokedTokenModel).filter_by(token_hash=h).first():
                s.add(RevokedTokenModel(token_hash=h, expires_at=expires))
                s.commit()
        finally:
            s.close()
    except Exception as e:  # noqa: BLE001
        logger.error(f"token_revocation: persist failed: {e}")


def is_token_revoked(token: str) -> bool:
    _load()
    _sweep()
    return _hash(token) in _revoked
