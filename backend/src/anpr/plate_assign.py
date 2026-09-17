"""
IBVAP — Attach detector-found number plates to vehicle tracks.

The coarse detector has a `license_plate` class (val mAP50 0.95). Plates are
kept out of the object tracker (a plate is part of a vehicle, not an object
that should enter zones) and each one is attached to the vehicle whose box
contains it. The crop is cut from the full-resolution frame with some padding,
which OCR reads far better than a plate guessed inside a small vehicle crop.
"""

from src.detection.detection_result import DetectionResult, FrameDetections

PLATE_CLASS = "license_plate"
VEHICLE_TYPES = frozenset({
    "car", "truck", "bus", "motorcycle", "vehicle", "military_ground_vehicle", "night_vision_object",
})
_PAD_X, _PAD_Y = 0.12, 0.25


def split_plates(frame: FrameDetections) -> tuple[FrameDetections, list[DetectionResult]]:
    plates = [d for d in frame.detections if d.class_name == PLATE_CLASS]
    if not plates:
        return frame, []
    objects = [d for d in frame.detections if d.class_name != PLATE_CLASS]
    return FrameDetections(frame.frame_id, frame.camera_id, frame.timestamp, objects), plates


def _inside(point, bbox) -> bool:
    x, y = point
    x1, y1, x2, y2 = bbox
    return x1 <= x <= x2 and y1 <= y <= y2


def _crop(frame, bbox):
    height, width = frame.shape[:2]
    x1, y1, x2, y2 = bbox
    pad_x, pad_y = int((x2 - x1) * _PAD_X), int((y2 - y1) * _PAD_Y)
    x1, y1 = max(0, x1 - pad_x), max(0, y1 - pad_y)
    x2, y2 = min(width, x2 + pad_x), min(height, y2 + pad_y)
    if x2 <= x1 or y2 <= y1:
        return None
    return frame[y1:y2, x1:x2].copy()


def assign_plates(tracks: dict, plates: list[DetectionResult], frame) -> None:
    """Keep, per vehicle track, the best plate view seen so far (confidence x size)."""
    if not plates:
        return
    vehicles = [t for t in tracks.values() if t.object_type in VEHICLE_TYPES]
    for plate in plates:
        owners = [t for t in vehicles if _inside(plate.centroid, t.bbox)]
        if not owners:
            continue
        # Nested/overlapping vehicles: the smallest box that contains the plate.
        owner = min(owners, key=lambda t: (t.bbox[2] - t.bbox[0]) * (t.bbox[3] - t.bbox[1]))
        score = plate.confidence * plate.area
        if score <= owner.plate_crop_score:
            continue
        crop = _crop(frame, plate.bbox)
        if crop is not None:
            owner.plate_crop = crop
            owner.plate_crop_score = score
