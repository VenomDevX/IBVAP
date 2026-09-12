"""
IBVAP — Face Detector
Face detection using InsightFace/RetinaFace.
"""

import numpy as np
from loguru import logger


class FaceDetector:
    """Face detection using InsightFace."""

    def __init__(self, model_name: str = "buffalo_l"):
        self._model = None
        self._model_name = model_name
        self._load_model()

    def _load_model(self):
        try:
            from insightface.app import FaceAnalysis

            self._model = FaceAnalysis(name=self._model_name, providers=["CPUExecutionProvider"])
            self._model.prepare(ctx_id=0, det_size=(640, 640))
            logger.success("Face detection model loaded")
        except ImportError:
            logger.warning("insightface not installed — face detection disabled")
        except Exception as e:
            logger.error(f"Face model load error: {e}")

    def detect_faces(self, frame: np.ndarray) -> list[dict]:
        """Detect faces in a frame. Returns list of face dicts."""
        if self._model is None:
            return []

        try:
            faces = self._model.get(frame)
            results = []
            for face in faces:
                bbox = face.bbox.astype(int).tolist()
                results.append(
                    {
                        "bbox": bbox,
                        "confidence": float(face.det_score),
                        "embedding": face.normed_embedding.tolist() if face.normed_embedding is not None else None,
                        "age": int(face.age) if hasattr(face, "age") else None,
                        "gender": "M"
                        if hasattr(face, "gender") and face.gender == 1
                        else "F"
                        if hasattr(face, "gender")
                        else None,
                    }
                )
            return results
        except Exception as e:
            logger.error(f"Face detection error: {e}")
            return []
