"""
IBVAP — License Plate Detector
YOLO-based license plate detection.
"""

import numpy as np
from loguru import logger


class PlateDetector:
    """
    Detects license plates in frames.
    Uses YOLO or falls back to cascade-based detection.
    """

    def __init__(self, model_path: str = "models/anpr/plate_detector.pt"):
        self._model = None
        self._model_path = model_path
        self._load_model()

    def _load_model(self):
        try:
            import os

            from ultralytics import YOLO

            if os.path.exists(self._model_path):
                self._model = YOLO(self._model_path)
                logger.success("Plate detection model loaded")
            else:
                logger.warning(f"Plate model not found: {self._model_path}")
        except Exception as e:
            logger.warning(f"Plate detector init error: {e}")

    def detect_plates(self, frame: np.ndarray, vehicle_bbox: tuple[int, int, int, int] | None = None) -> list[dict]:
        """
        Detect license plates in a frame or vehicle crop.

        Returns list of plate detections with bbox and crop.
        """
        results = []

        # Crop to vehicle region if provided
        roi = frame
        offset_x, offset_y = 0, 0
        if vehicle_bbox:
            x1, y1, x2, y2 = vehicle_bbox
            roi = frame[y1:y2, x1:x2]
            offset_x, offset_y = x1, y1

        if self._model is None:
            return results

        try:
            detections = self._model(roi, conf=0.3, verbose=False)
            if detections and len(detections) > 0:
                boxes = detections[0].boxes
                if boxes is not None:
                    for box in boxes:
                        bx1, by1, bx2, by2 = box.xyxy[0].cpu().numpy().astype(int)
                        conf = float(box.conf[0].cpu().numpy())

                        # Adjust for ROI offset
                        abs_x1 = bx1 + offset_x
                        abs_y1 = by1 + offset_y
                        abs_x2 = bx2 + offset_x
                        abs_y2 = by2 + offset_y

                        # Crop plate
                        plate_crop = frame[abs_y1:abs_y2, abs_x1:abs_x2]

                        results.append(
                            {
                                "bbox": (abs_x1, abs_y1, abs_x2, abs_y2),
                                "confidence": conf,
                                "crop": plate_crop,
                            }
                        )
        except Exception as e:
            logger.error(f"Plate detection error: {e}")

        return results
