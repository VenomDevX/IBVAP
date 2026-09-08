"""
IBVAP — Evidence integrity

Append-only HMAC hash chain over the alert / event tables. Each row commits to
the previous row's hash, so altering ANY row (or reordering) breaks every later
link and is detectable by `scripts/verify_evidence_chain.py`.

Honest scope: this makes the DB tamper-EVIDENT, not tamper-PROOF. An attacker who
also holds `EVIDENCE_HMAC_KEY` can rewrite the whole chain. For production,
combine with a KMS-held key and periodic anchoring of the chain head to external
WORM storage (see docs/IBVAP_TRD.md).
"""

import hashlib
import hmac
import json
import os

from loguru import logger

_KEY_ENV = "EVIDENCE_HMAC_KEY"
GENESIS = "0" * 64
_ephemeral: bytes | None = None
_warned = False


def _key() -> bytes:
    global _ephemeral, _warned
    k = os.getenv(_KEY_ENV)
    if k:
        return k.encode()
    if _ephemeral is None:
        _ephemeral = os.urandom(32)
    if not _warned:
        logger.warning(
            f"{_KEY_ENV} not set — using a per-boot random key. The evidence chain "
            "still detects tampering within this run but cannot be verified across restarts."
        )
        _warned = True
    return _ephemeral


def _canonical(record: dict) -> str:
    return json.dumps(record, sort_keys=True, separators=(",", ":"), default=str)


def compute_hash(record: dict, prev_hash: str | None) -> str:
    """HMAC-SHA256 of the canonical record bound to the previous hash."""
    msg = (_canonical(record) + (prev_hash or GENESIS)).encode()
    return hmac.new(_key(), msg, hashlib.sha256).hexdigest()


def verify(record: dict, prev_hash: str | None, stored_hash: str) -> bool:
    if not stored_hash:
        return False
    return hmac.compare_digest(compute_hash(record, prev_hash), stored_hash)


def sha256_file(path: str) -> str | None:
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None
