"""
IBVAP — Face recognition orchestrator

Wraps FaceDetector + FaceMatcher for the pipeline: given a person crop it returns
the best gallery match. Disabled by default (`face.enabled` in thresholds.yaml)
because it needs `insightface` + the buffalo_l model (~300 MB). When enabled but
the dependency is missing it degrades to a no-op.
"""

import numpy as np
from loguru import logger


class FaceRecognizer:
    def __init__(
        self,
        enabled: bool = False,
        gallery_path: str = "./models/face/gallery.json",
        similarity_threshold: float = 0.45,
        uncertain_threshold: float = 0.35,
        min_face_confidence: float = 0.6,
    ):
        self.enabled = enabled
        self.min_face_confidence = min_face_confidence
        self._detector = None
        self._matcher = None
        if not enabled:
            return
        try:
            from src.face.face_detector import FaceDetector
            from src.face.face_matcher import FaceMatcher

            self._detector = FaceDetector()
            self._matcher = FaceMatcher(
                gallery_path=gallery_path,
                similarity_threshold=similarity_threshold,
                uncertain_threshold=uncertain_threshold,
            )
            if self._detector._model is None:
                logger.warning("FaceRecognizer enabled but insightface model unavailable — disabling")
                self.enabled = False
        except Exception as e:  # noqa: BLE001
            logger.warning(f"FaceRecognizer init failed ({e}) — disabling")
            self.enabled = False

    @property
    def active(self) -> bool:
        return bool(self.enabled and self._detector is not None and self._matcher is not None)

    def identify(self, person_crop: np.ndarray) -> dict | None:
        """Return {"identity", "similarity", "status"} for the most confident face,
        or None if no usable face is found."""
        if not self.active or person_crop is None or getattr(person_crop, "size", 0) == 0:
            return None
        try:
            faces = self._detector.detect_faces(person_crop)
        except Exception as e:  # noqa: BLE001
            logger.debug(f"face detect error: {e}")
            return None
        faces = [f for f in faces if f.get("confidence", 0) >= self.min_face_confidence and f.get("embedding")]
        if not faces:
            return None
        best = max(faces, key=lambda f: f["confidence"])
        return self._matcher.match(best)
