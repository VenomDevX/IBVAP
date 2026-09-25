"""
IBVAP — Face Matcher
Matches face embeddings against an authorized gallery.
"""

import json
import os

import numpy as np
from loguru import logger

from src.face.face_embedder import FaceEmbedder


class FaceMatcher:
    """
    Matches face embeddings against a gallery of known/authorized identities.
    Results: known / unknown / uncertain.
    """

    def __init__(
        self,
        gallery_path: str = "./models/face/gallery.json",
        similarity_threshold: float = 0.45,
        uncertain_threshold: float = 0.35,
    ):
        self.gallery_path = gallery_path
        self.similarity_threshold = similarity_threshold
        self.uncertain_threshold = uncertain_threshold
        self.embedder = FaceEmbedder()

        # Gallery: {identity_label: [embeddings]}
        self._gallery: dict[str, list[np.ndarray]] = {}
        self._load_gallery()

    def _load_gallery(self):
        """Load authorized face gallery from file.

        Accepts the documented format ``{"identities": [{"name", "embedding"}]}``
        (an entry may also carry an ``embeddings`` list) and the older flat
        ``{label: [embedding, ...]}`` map. Keys starting with ``_`` are comments.
        """
        if not os.path.exists(self.gallery_path):
            return
        try:
            with open(self.gallery_path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            logger.error(f"Gallery load error: {e}")
            return

        if isinstance(data.get("identities"), list):
            entries = []
            for item in data["identities"]:
                vectors = item.get("embeddings") or ([item["embedding"]] if "embedding" in item else [])
                entries.append((item.get("name"), vectors))
        else:
            entries = [(label, embs) for label, embs in data.items() if not label.startswith("_")]

        for label, vectors in entries:
            try:
                arrays = [np.asarray(v, dtype=np.float32) for v in vectors]
            except (TypeError, ValueError) as e:
                logger.error(f"Gallery entry {label!r} skipped: {e}")
                continue
            if label and arrays:
                self._gallery.setdefault(str(label), []).extend(arrays)
        logger.info(f"Loaded face gallery: {len(self._gallery)} identities")

    def match(self, face_data: dict) -> dict:
        """
        Match a detected face against the gallery.

        Returns:
            {"identity": str, "similarity": float, "status": "known"|"unknown"|"uncertain"}
        """
        embedding = self.embedder.get_embedding(face_data)
        if embedding is None:
            return {"identity": "no_embedding", "similarity": 0.0, "status": "unknown"}

        if not self._gallery:
            return {"identity": "no_gallery", "similarity": 0.0, "status": "unknown"}

        best_label = "unknown"
        best_sim = 0.0

        for label, gallery_embs in self._gallery.items():
            for g_emb in gallery_embs:
                sim = self.embedder.cosine_similarity(embedding, g_emb)
                if sim > best_sim:
                    best_sim = sim
                    best_label = label

        if best_sim >= self.similarity_threshold:
            return {"identity": best_label, "similarity": round(best_sim, 3), "status": "known"}
        elif best_sim >= self.uncertain_threshold:
            return {"identity": best_label, "similarity": round(best_sim, 3), "status": "uncertain"}
        else:
            return {"identity": "unknown", "similarity": round(best_sim, 3), "status": "unknown"}

    def add_to_gallery(self, label: str, embedding: np.ndarray):
        """Add a face embedding to the gallery."""
        if label not in self._gallery:
            self._gallery[label] = []
        self._gallery[label].append(embedding)
        self._save_gallery()

    def _save_gallery(self):
        """Save gallery to file."""
        try:
            os.makedirs(os.path.dirname(self.gallery_path), exist_ok=True)
            data = {
                "_info": "IBVAP Face Gallery — add entries with: name, embedding (512-dim ArcFace vector)",
                "identities": [
                    {"name": label, "embeddings": [e.tolist() for e in embs]} for label, embs in self._gallery.items()
                ],
            }
            with open(self.gallery_path, "w", encoding="utf-8") as f:
                json.dump(data, f)
        except Exception as e:
            logger.error(f"Gallery save error: {e}")
