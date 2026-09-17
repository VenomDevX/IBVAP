"""
IBVAP — Watchlist matching.

Keeps the active watchlist in memory (plates by text, faces as one normalised
matrix) and answers match queries from the pipeline's enrichment threads.
`load()` swaps in a fresh snapshot in one assignment, so readers never see a
half-built list.
"""

import re
import threading
from dataclasses import dataclass

import numpy as np
from loguru import logger

from src.database.models import WatchlistEntryModel
from src.watchlist import crypto

LIST_TYPES = ("wanted", "authorized", "vip")

_NON_ALNUM = re.compile(r"[^A-Z0-9]")
# Characters OCR routinely confuses on number plates, folded to one symbol.
_CONFUSABLE = str.maketrans({
    "O": "0", "Q": "0", "D": "0", "I": "1", "L": "1", "Z": "2", "S": "5", "B": "8", "G": "6",
})


def normalize_plate(text: str | None) -> str:
    return _NON_ALNUM.sub("", (text or "").upper())


def canonical_plate(text: str | None) -> str:
    return normalize_plate(text).translate(_CONFUSABLE)


@dataclass(frozen=True)
class WatchlistHit:
    entry_id: str
    kind: str
    list_type: str
    label: str
    score: float = 1.0
    exact: bool = True

    def to_dict(self) -> dict:
        return {
            "entry_id": self.entry_id,
            "kind": self.kind,
            "list_type": self.list_type,
            "label": self.label,
            "score": round(self.score, 3),
            "exact": self.exact,
        }


@dataclass(frozen=True)
class _Snapshot:
    plates_exact: dict
    plates_canonical: dict
    face_matrix: np.ndarray | None
    face_hits: tuple


class WatchlistService:
    def __init__(self, face_threshold: float = 0.45):
        self.face_threshold = float(face_threshold)
        self._snapshot = _Snapshot({}, {}, None, ())
        self._lock = threading.Lock()
        self.version = 0
        self.skipped_entries = 0

    def load(self, session) -> None:
        rows = (
            session.query(WatchlistEntryModel)
            .filter_by(active=True)
            .order_by(WatchlistEntryModel.id)
            .all()
        )
        exact, canonical, vectors, face_hits = {}, {}, [], []
        skipped = 0
        for row in rows:
            if row.kind == "plate" and row.plate:
                hit = WatchlistHit(row.entry_id, "plate", row.list_type, row.label)
                exact.setdefault(row.plate, hit)
                canonical.setdefault(canonical_plate(row.plate), hit)
            elif row.kind == "face" and row.embedding_enc:
                try:
                    vector = crypto.decrypt_embedding(row.embedding_enc)
                except crypto.WatchlistKeyError:
                    skipped += 1
                    continue
                norm = float(np.linalg.norm(vector))
                if norm == 0:
                    skipped += 1
                    continue
                vectors.append(vector / norm)
                face_hits.append(WatchlistHit(row.entry_id, "face", row.list_type, row.label))
        if skipped:
            logger.warning("Watchlist: {} face entries could not be decrypted and are ignored", skipped)

        matrix = None
        if vectors:
            sizes = {v.shape[0] for v in vectors}
            if len(sizes) == 1:
                matrix = np.stack(vectors)
            else:
                logger.error("Watchlist: face embeddings have mixed sizes {}; face matching disabled", sorted(sizes))
        with self._lock:
            self._snapshot = _Snapshot(exact, canonical, matrix, tuple(face_hits))
            self.skipped_entries = skipped
            self.version += 1

    def match_plate(self, text: str | None) -> WatchlistHit | None:
        plate = normalize_plate(text)
        if not plate:
            return None
        snap = self._snapshot
        hit = snap.plates_exact.get(plate)
        if hit is not None:
            return hit
        fuzzy = snap.plates_canonical.get(canonical_plate(plate))
        if fuzzy is None:
            return None
        return WatchlistHit(fuzzy.entry_id, fuzzy.kind, fuzzy.list_type, fuzzy.label, score=0.9, exact=False)

    def match_face(self, embedding) -> WatchlistHit | None:
        snap = self._snapshot
        if embedding is None or snap.face_matrix is None:
            return None
        vector = np.asarray(embedding, dtype=np.float32).ravel()
        if vector.shape[0] != snap.face_matrix.shape[1]:
            return None
        norm = float(np.linalg.norm(vector))
        if norm == 0:
            return None
        sims = snap.face_matrix @ (vector / norm)
        best = int(np.argmax(sims))
        score = float(sims[best])
        if score < self.face_threshold:
            return None
        base = snap.face_hits[best]
        return WatchlistHit(base.entry_id, base.kind, base.list_type, base.label, score=score)

    @property
    def size(self) -> dict:
        snap = self._snapshot
        return {"plates": len(snap.plates_exact), "faces": len(snap.face_hits)}


_service: WatchlistService | None = None
_service_lock = threading.Lock()


def get_watchlist() -> WatchlistService:
    global _service
    with _service_lock:
        if _service is None:
            _service = WatchlistService()
        return _service


def reload_watchlist() -> WatchlistService:
    """Reload the shared service from the database (call after any change)."""
    from src.database.db import get_database

    service = get_watchlist()
    with get_database().get_session() as session:
        service.load(session)
    return service
