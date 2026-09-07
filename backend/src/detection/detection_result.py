"""
IBVAP — Detection Result Data Class
Standardized detection output format.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np


@dataclass
class DetectionResult:
    """A single object detection result."""
    bbox: Tuple[int, int, int, int]  # (x1, y1, x2, y2)
    class_id: int
    class_name: str
    confidence: float
    centroid: Tuple[int, int] = field(init=False)

    def __post_init__(self):
        x1, y1, x2, y2 = self.bbox
        self.centroid = ((x1 + x2) // 2, (y1 + y2) // 2)

    @property
    def width(self) -> int:
        return self.bbox[2] - self.bbox[0]

    @property
    def height(self) -> int:
        return self.bbox[3] - self.bbox[1]

    @property
    def area(self) -> int:
        return self.width * self.height

    def to_dict(self) -> dict:
        return {
            "bbox": list(self.bbox),
            "class_id": self.class_id,
            "class_name": self.class_name,
            "confidence": round(self.confidence, 3),
            "centroid": list(self.centroid),
        }


@dataclass
class FrameDetections:
    """All detections for a single frame."""
    frame_id: int
    camera_id: str
    timestamp: float
    detections: List[DetectionResult] = field(default_factory=list)

    @property
    def person_count(self) -> int:
        return sum(1 for d in self.detections if d.class_name == "person")

    @property
    def vehicle_count(self) -> int:
        vehicle_classes = {"car", "motorcycle", "bus", "truck"}
        return sum(1 for d in self.detections if d.class_name in vehicle_classes)

    def get_by_class(self, class_name: str) -> List[DetectionResult]:
        return [d for d in self.detections if d.class_name == class_name]

    def to_numpy(self) -> np.ndarray:
        """Convert detections to numpy array for tracker input.
        Format: [[x1, y1, x2, y2, confidence, class_id], ...]
        """
        if not self.detections:
            return np.empty((0, 6))
        return np.array([
            [*d.bbox, d.confidence, d.class_id]
            for d in self.detections
        ], dtype=np.float32)
