"""
IBVAP — ANPR (automatic number-plate recognition)

`extract_plate(vehicle_crop)` -> {"text", "confidence", "bbox"}:
  1. localise the plate inside the vehicle crop — a YOLO plate model if
     `models/anpr/plate_detector.pt` exists, else a contour heuristic;
  2. OCR the plate region via `src.anpr.ocr` (EasyOCR / PaddleOCR / tesseract).

`extract_license_plate(crop) -> str` is the thin wrapper the pipeline calls today.
"""

from collections import defaultdict

import numpy as np

from src.anpr.ocr import read_plate
from src.anpr.plate_detector import PlateDetector
from src.anpr.plate_format import parse_plate

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


def extract_plate(vehicle_crop: np.ndarray, strict_format: bool = True, plate_located: bool = False) -> dict:
    """strict_format: only accept reads that fit an Indian plate format
    (drops signboards and partial reads); off keeps foreign plates too.
    plate_located: the image is already a plate (found by the detector), so
    skip localisation and OCR it as is."""
    if vehicle_crop is None or getattr(vehicle_crop, "size", 0) == 0:
        return {"text": "Unknown", "confidence": 0.0, "bbox": None, "format": "unknown"}

    plate_bbox = None
    det = None if plate_located else _plate_detector()
    if plate_located:
        plate_img = vehicle_crop
    elif det is not None:
        plates = det.detect_plates(vehicle_crop)
        if plates:
            best = max(plates, key=lambda p: p["confidence"])
            plate_img, plate_bbox = best["crop"], best["bbox"]
        else:
            plate_img = _contour_plate_crop(vehicle_crop)
    else:
        plate_img = _contour_plate_crop(vehicle_crop)

    text, conf = read_plate(plate_img)
    reading = parse_plate(text)
    if reading.valid:
        # Each positional correction makes the read a little less certain.
        text, conf = reading.text, round(conf * 0.95 ** reading.corrections, 3)
    elif strict_format:
        text, conf = "", 0.0
    else:
        text = reading.text
    return {
        "text": text or "Unknown",
        "confidence": conf,
        "bbox": list(plate_bbox) if plate_bbox is not None else None,
        "format": reading.kind,
    }


def extract_license_plate(crop: np.ndarray) -> str:
    """Backwards-compatible: plate string only ('Unknown' if nothing legible)."""
    return extract_plate(crop)["text"]


class PlateConsensus:
    """Confidence-weighted multi-frame OCR consensus without inventing text."""

    def __init__(self, min_observations: int = 3, min_confidence: float = 0.55, max_observations: int = 12):
        self.min_observations = max(1, int(min_observations))
        self.min_confidence = float(min_confidence)
        self.max_observations = max(self.min_observations, int(max_observations))

    def add(self, track, text: str, confidence: float) -> tuple[str, float]:
        normalized = "".join(ch for ch in (text or "").upper() if ch.isalnum())
        if not normalized or normalized == "UNKNOWN" or confidence <= 0:
            return "UNKNOWN", 0.0
        track.plate_observations.append({"text": normalized, "confidence": float(confidence)})
        track.plate_observations = track.plate_observations[-self.max_observations :]
        if len(track.plate_observations) < self.min_observations:
            return "UNKNOWN", 0.0
        votes = defaultdict(float)
        counts = defaultdict(int)
        for observation in track.plate_observations:
            votes[observation["text"]] += observation["confidence"]
            counts[observation["text"]] += 1
        winner = max(votes, key=lambda value: (votes[value], counts[value]))
        consensus = counts[winner] / len(track.plate_observations)
        confidence = votes[winner] / counts[winner]
        if counts[winner] < self.min_observations or consensus < 0.5 or confidence < self.min_confidence:
            return "UNKNOWN", 0.0
        return winner, round(confidence * consensus, 3)
