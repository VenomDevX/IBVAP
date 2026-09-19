"""Detector-found plates are attached to their vehicle and read directly."""

import numpy as np

from src.anpr.plate_assign import assign_plates, split_plates
from src.detection.detection_result import DetectionResult, FrameDetections
from src.tracking.track import Track


def _det(name, bbox, conf=0.9, cls=0):
    return DetectionResult(bbox=bbox, class_id=cls, class_name=name, confidence=conf)


def _vehicle(tid=1, bbox=(100, 100, 300, 250), kind="car"):
    return Track(tid, kind, "c", bbox=bbox)


def test_split_removes_plates_from_tracking_input():
    frame = FrameDetections(1, "c", 5.0, [_det("car", (0, 0, 50, 50)), _det("license_plate", (10, 30, 30, 40), cls=6)])
    objects, plates = split_plates(frame)
    assert [d.class_name for d in objects.detections] == ["car"]
    assert (objects.frame_id, objects.camera_id, objects.timestamp) == (1, "c", 5.0)
    assert [d.class_name for d in plates] == ["license_plate"]


def test_plate_is_attached_to_the_vehicle_containing_it():
    frame = np.arange(400 * 400 * 3, dtype=np.uint32).reshape(400, 400, 3).astype(np.uint8)
    car, other = _vehicle(1), _vehicle(2, bbox=(310, 100, 390, 250))
    person = Track(3, "person", "c", bbox=(100, 100, 300, 250))
    plate = _det("license_plate", (180, 210, 240, 230))
    assign_plates({1: car, 2: other, 3: person}, [plate], frame)

    assert car.plate_crop is not None
    # Cropped from the full frame with padding around the box.
    assert car.plate_crop.shape[0] > 20 and car.plate_crop.shape[1] > 60
    assert other.plate_crop is None
    assert getattr(person, "plate_crop", None) is None


def test_better_plate_view_replaces_worse_one():
    frame = np.zeros((400, 400, 3), np.uint8)
    car = _vehicle()
    assign_plates({1: car}, [_det("license_plate", (180, 210, 220, 222), conf=0.5)], frame)
    first = car.plate_crop_score
    assign_plates({1: car}, [_det("license_plate", (170, 205, 250, 235), conf=0.9)], frame)
    assert car.plate_crop_score > first
    better = car.plate_crop_score
    assign_plates({1: car}, [_det("license_plate", (180, 210, 200, 216), conf=0.3)], frame)
    assert car.plate_crop_score == better


def test_plate_outside_every_vehicle_is_ignored():
    frame = np.zeros((400, 400, 3), np.uint8)
    car = _vehicle()
    assign_plates({1: car}, [_det("license_plate", (5, 5, 40, 20))], frame)
    assert car.plate_crop is None


def test_extract_plate_reads_located_plate_directly(monkeypatch):
    import src.features.anpr as anpr

    def fail(*_a, **_k):
        raise AssertionError("localisation must be skipped for a detector-located plate")

    monkeypatch.setattr(anpr, "_plate_detector", fail)
    monkeypatch.setattr(anpr, "_contour_plate_crop", fail)
    monkeypatch.setattr(anpr, "read_plate", lambda img: ("KA05MN9999", 0.8))
    out = anpr.extract_plate(np.zeros((30, 90, 3), np.uint8), plate_located=True)
    assert out["text"] == "KA05MN9999"


def test_pipeline_ocrs_the_located_plate(tmp_path, monkeypatch):
    from unittest.mock import Mock

    from src.alerts.alert_engine import AlertEngine
    from src.ingestion.video_source import CameraInfo
    from src.pipeline import pipeline as pipeline_mod
    from src.pipeline.pipeline import CameraPipeline
    from src.spatial.fence_detector import FenceDetector
    from src.spatial.zone_manager import ZoneManager

    seen = {}

    def fake_extract(crop, strict_format=True, plate_located=False):
        seen["shape"], seen["located"] = crop.shape, plate_located
        return {"text": "KA05MN9999", "confidence": 0.9}

    monkeypatch.setattr(pipeline_mod, "extract_plate", fake_extract)
    cam = CameraPipeline(CameraInfo("c", "C", "rtsp://x"), Mock(), ZoneManager(), FenceDetector(), {},
                         AlertEngine(snapshots_dir=str(tmp_path)))
    car = _vehicle()
    car.best_frame = np.zeros((150, 200, 3), np.uint8)
    car.plate_crop = np.zeros((36, 96, 3), np.uint8)
    cam._run_anpr_check(car)
    assert seen == {"shape": (36, 96, 3), "located": True}


def test_vehicle_without_detected_plate_is_not_ocrd_by_default(tmp_path, monkeypatch):
    from unittest.mock import Mock

    from src.alerts.alert_engine import AlertEngine
    from src.ingestion.video_source import CameraInfo
    from src.pipeline import pipeline as pipeline_mod
    from src.pipeline.pipeline import CameraPipeline
    from src.spatial.fence_detector import FenceDetector
    from src.spatial.zone_manager import ZoneManager

    calls = []
    monkeypatch.setattr(pipeline_mod, "extract_plate", lambda crop, **kw: calls.append(kw) or {"text": "Unknown", "confidence": 0})
    cam = CameraPipeline(CameraInfo("c", "C", "rtsp://x"), Mock(), ZoneManager(), FenceDetector(), {},
                         AlertEngine(snapshots_dir=str(tmp_path)))
    car = _vehicle()
    car.best_frame = np.zeros((150, 200, 3), np.uint8)
    assert not cam._anpr_due(car)
    car.plate_crop = np.zeros((30, 90, 3), np.uint8)
    assert cam._anpr_due(car)

    loose = CameraPipeline(CameraInfo("d", "D", "rtsp://x"), Mock(), ZoneManager(), FenceDetector(), {},
                           AlertEngine(snapshots_dir=str(tmp_path)),
                           thresholds={"anpr": {"require_detected_plate": False}})
    guess = _vehicle()
    guess.best_frame_score = 0.5
    assert loose._anpr_due(guess)
