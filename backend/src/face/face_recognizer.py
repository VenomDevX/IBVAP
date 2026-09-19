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
        device: str = "auto",
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

            self._detector = FaceDetector(device=device)
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

    def faces(self, image: np.ndarray) -> list[dict]:
        """All usable faces (confidence-gated, with an embedding), best first."""
        if not self.active or image is None or getattr(image, "size", 0) == 0:
            return []
        try:
            faces = self._detector.detect_faces(image)
        except Exception as e:  # noqa: BLE001
            logger.debug(f"face detect error: {e}")
            return []
        faces = [f for f in faces if f.get("confidence", 0) >= self.min_face_confidence and f.get("embedding")]
        return sorted(faces, key=lambda f: f["confidence"], reverse=True)

    def best_face(self, person_crop: np.ndarray) -> dict | None:
        faces = self.faces(person_crop)
        return faces[0] if faces else None

    def match(self, face: dict) -> dict:
        """Gallery match for one face from faces()/best_face()."""
        return self._matcher.match(face)

    def identify(self, person_crop: np.ndarray) -> dict | None:
        """Return {"identity", "similarity", "status"} for the most confident face,
        or None if no usable face is found."""
        best = self.best_face(person_crop)
        return self.match(best) if best is not None else None
