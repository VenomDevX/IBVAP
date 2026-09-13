"""Deterministic representative-crop quality scoring."""

import cv2
import numpy as np


def score_crop(crop: np.ndarray, confidence: float, frame_shape: tuple | None = None, bbox: tuple | None = None) -> float:
    if crop is None or getattr(crop, "size", 0) == 0:
        return 0.0
    height, width = crop.shape[:2]
    if height < 12 or width < 12:
        return 0.0
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
    sharpness = min(float(cv2.Laplacian(gray, cv2.CV_64F).var()) / 500.0, 1.0)
    size_score = min((height * width) / (320.0 * 320.0), 1.0)
    brightness = float(np.mean(gray))
    visibility = 1.0 if 25 <= brightness <= 235 else 0.35
    edge_score = 1.0
    if frame_shape is not None and bbox is not None:
        frame_h, frame_w = frame_shape[:2]
        x1, y1, x2, y2 = bbox
        margin = max(2, int(min(frame_h, frame_w) * 0.005))
        touches = sum((x1 <= margin, y1 <= margin, x2 >= frame_w - margin, y2 >= frame_h - margin))
        edge_score = max(0.2, 1.0 - touches * 0.22)
    return round(
        0.42 * max(0.0, min(float(confidence), 1.0))
        + 0.23 * size_score
        + 0.25 * sharpness
        + 0.05 * visibility
        + 0.05 * edge_score,
        4,
    )


def update_best_frame(track, crop: np.ndarray, frame_shape: tuple, bbox: tuple, timestamp: float) -> bool:
    score = score_crop(crop, track.confidence, frame_shape, bbox)
    if score <= track.best_frame_score:
        return False
    track.best_frame_score = score
    track.best_frame_timestamp = timestamp
    track.best_frame = crop.copy()
    return True
