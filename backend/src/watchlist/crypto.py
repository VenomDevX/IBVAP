"""
Encryption of watchlist face embeddings (biometric data) at rest.

Key: `WATCHLIST_ENCRYPTION_KEY` (a Fernet key) if set, otherwise derived from
`EVIDENCE_HMAC_KEY` with HKDF so a dev setup works without another secret.
Without either there is no stable key, so enrolment is refused rather than
storing data that could never be read back.
"""

import base64
import os

import numpy as np
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


class WatchlistKeyError(RuntimeError):
    """No usable key, or data encrypted under a different key."""


def _fernet() -> Fernet:
    explicit = os.getenv("WATCHLIST_ENCRYPTION_KEY", "").strip()
    if explicit:
        try:
            return Fernet(explicit.encode())
        except ValueError as exc:
            raise WatchlistKeyError("WATCHLIST_ENCRYPTION_KEY is not a valid Fernet key") from exc
    base = os.getenv("EVIDENCE_HMAC_KEY", "").strip()
    if not base:
        raise WatchlistKeyError("set WATCHLIST_ENCRYPTION_KEY (or EVIDENCE_HMAC_KEY) to store face embeddings")
    derived = HKDF(algorithm=hashes.SHA256(), length=32, salt=b"ibvap-watchlist-v1", info=b"face-embeddings")
    return Fernet(base64.urlsafe_b64encode(derived.derive(base.encode())))


def encrypt_embedding(embedding) -> str:
    vector = np.asarray(embedding, dtype=np.float32).ravel()
    return _fernet().encrypt(vector.tobytes()).decode()


def decrypt_embedding(token: str) -> np.ndarray:
    try:
        raw = _fernet().decrypt(token.encode())
    except InvalidToken as exc:
        raise WatchlistKeyError("face embedding was encrypted with a different key") from exc
    return np.frombuffer(raw, dtype=np.float32).copy()
