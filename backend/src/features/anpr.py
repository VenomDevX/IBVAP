"""
IBVAP — ANPR (automatic number-plate recognition)

`extract_plate(vehicle_crop)` -> {"text", "confidence", "bbox"}:
  1. localise the plate inside the vehicle crop — a YOLO plate model if
     `models/anpr/plate_detector.pt` exists, else a contour heuristic;
  2. OCR the plate region via `src.anpr.ocr` (EasyOCR / PaddleOCR / tesseract).

`extract_license_plate(crop) -> str` is the thin wrapper the pipeline calls today.
"""

import numpy as np

from src.anpr.ocr import read_plate
from src.anpr.plate_detector import PlateDetector

_detector: PlateDetector | None = None
_detector_tried = False


def _plate_detector() -> PlateDetector | None:
    global _detector, _detector_tried
    if not _detector_tried:
        _detector_tried = True
        try:
            d = PlateDetector()
            _detector = d if d._model is not None else None
        except Exception:
            _detector = None
    return _detector


def _contour_plate_crop(crop: np.ndarray) -> np.ndarray:
    """Heuristic: largest 4-corner contour in the lower half of the vehicle crop."""
    import cv2

    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
    edged = cv2.Canny(cv2.bilateralFilter(gray, 11, 17, 17), 30, 200)
    cnts, _ = cv2.findContours(edged, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    for c in sorted(cnts, key=cv2.contourArea, reverse=True)[:10]:
        approx = cv2.approxPolyDP(c, 10, True)
        if len(approx) == 4:
            x, y, w, h = cv2.boundingRect(approx)
            if w > h and w * h > 0.01 * crop.shape[0] * crop.shape[1]:
                return crop[y : y + h, x : x + w]
    return crop


def extract_plate(vehicle_crop: np.ndarray) -> dict:
    if vehicle_crop is None or getattr(vehicle_crop, "size", 0) == 0:
        return {"text": "Unknown", "confidence": 0.0, "bbox": None}

    plate_bbox = None
    det = _plate_detector()
    if det is not None:
        plates = det.detect_plates(vehicle_crop)
        if plates:
            best = max(plates, key=lambda p: p["confidence"])
            plate_img, plate_bbox = best["crop"], best["bbox"]
        else:
            plate_img = _contour_plate_crop(vehicle_crop)
    else:
        plate_img = _contour_plate_crop(vehicle_crop)

    text, conf = read_plate(plate_img)
    return {
        "text": text or "Unknown",
        "confidence": conf,
        "bbox": list(plate_bbox) if plate_bbox is not None else None,
    }


def extract_license_plate(crop: np.ndarray) -> str:
    """Backwards-compatible: plate string only ('Unknown' if nothing legible)."""
    return extract_plate(crop)["text"]
