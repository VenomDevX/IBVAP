"""
IBVAP — Face Embedder
ArcFace embedding generation for face recognition.
"""

import numpy as np


class FaceEmbedder:
    """Generates ArcFace face embeddings."""

    def __init__(self):
        self._model = None

    def get_embedding(self, face_data: dict) -> np.ndarray | None:
        """Extract embedding from a detected face."""
        embedding = face_data.get("embedding")
        if embedding is not None:
            return np.array(embedding, dtype=np.float32)
        return None

    @staticmethod
    def cosine_similarity(emb1: np.ndarray, emb2: np.ndarray) -> float:
        """Calculate cosine similarity between two embeddings."""
        dot = np.dot(emb1, emb2)
        norm1 = np.linalg.norm(emb1)
        norm2 = np.linalg.norm(emb2)
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return float(dot / (norm1 * norm2))
