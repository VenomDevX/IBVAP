"""
IBVAP — YOLOv8 Object Detector
Wrapper around Ultralytics YOLO for person/vehicle detection.
"""

import os
import threading
import time
from collections import deque

import cv2
import numpy as np
from loguru import logger

from src.paths import output_dir

# Ultralytics otherwise writes global user configuration during import. Runtime
# state belongs in the configured project data root and must remain writable in
# containers/restricted service accounts.
_ultralytics_config_dir = output_dir() / "ultralytics"
_ultralytics_config_dir.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("YOLO_CONFIG_DIR", str(_ultralytics_config_dir))

try:
    from ultralytics import YOLO
except ImportError:
    YOLO = None
    logger.warning("ultralytics not installed — detector will use mock mode")

from src.detection.detection_result import DetectionResult, FrameDetections

# COCO class names for the classes we care about (stock yolov8n fallback)
COCO_TARGET_CLASSES: dict[int, str] = {
    0: "person",
    1: "bicycle",
    2: "car",
    3: "motorcycle",
    5: "bus",
    7: "truck",
}

try:
    from ml.taxonomy import normalize as _normalize_class
except Exception:  # ml package not importable (e.g. isolated tests)

    def _normalize_class(name: str) -> str:  # type: ignore
        return (name or "unknown").strip().lower().replace(" ", "_")


class ObjectDetector:
    """
    YOLO-based object detector.
    Detects people, vehicles, and other configurable object classes.

    With a stock model it filters to COCO person/vehicle ids. With a custom
    coarse model (weights_path set + detect_all=True) it reads the model's own
    `names` map and emits every class, normalised to the pipeline vocabulary.
    """

    def __init__(
        self,
        model_path: str = "yolov8n.pt",
        confidence_threshold: float = 0.40,
        nms_threshold: float = 0.45,
        target_classes: list[int] | None = None,
        device: str = "auto",
        imgsz: int = 640,
        detect_all: bool = False,
    ):
        self.confidence_threshold = confidence_threshold
        self.nms_threshold = nms_threshold
        self.target_classes = target_classes or [0, 2, 3, 5, 7]
        self.detect_all = detect_all
        self.imgsz = imgsz
        self._model = None
        self._device = device
        self._model_path = model_path
        # A single detector is shared by all camera threads. Serial inference
        # avoids overlapping CUDA/CPU allocations and predictor races.
        self._inference_lock = threading.Lock()
        # id -> canonical class name; populated from the model after load
        self._id2name: dict[int, str] = {k: _normalize_class(v) for k, v in COCO_TARGET_CLASSES.items()}

        # Performance tracking
        self._inference_times = deque(maxlen=200)
        self._total_detections: int = 0

        self._load_model()

    def _load_model(self):
        """Load the YOLO model."""
        if YOLO is None:
            logger.warning("YOLO not available — running in mock mode")
            return

        try:
            logger.info(f"Loading detection model: {self._model_path}")
            self._model = YOLO(self._model_path)

            # Auto-detect device
            if self._device == "auto":
                import torch

                self._device = "cuda" if torch.cuda.is_available() else "cpu"

            # Prefer the model's own class names (custom coarse model)
            model_names = getattr(self._model, "names", None)
            if model_names:
                self._id2name = {int(k): _normalize_class(v) for k, v in dict(model_names).items()}

            logger.success(
                f"Detection model loaded on {self._device} ({len(self._id2name)} classes, detect_all={self.detect_all})"
            )

        except Exception as e:
            logger.error(f"Failed to load detection model: {e}")
            self._model = None

    def detect(self, frame: np.ndarray, frame_id: int = 0, camera_id: str = "") -> FrameDetections:
        """
        Run object detection on a single frame.

        Args:
            frame: BGR image (numpy array)
            frame_id: Frame sequence number
            camera_id: Camera identifier

        Returns:
            FrameDetections containing all detected objects
        """
        timestamp = time.time()
        detections: list[DetectionResult] = []

        if self._model is None:
            return FrameDetections(frame_id=frame_id, camera_id=camera_id, timestamp=timestamp, detections=detections)

        try:
            start_time = time.time()

            # Run inference
            with self._inference_lock:
                results = self._model(
                    frame,
                    conf=self.confidence_threshold,
                    iou=self.nms_threshold,
                    imgsz=self.imgsz,
                    device=self._device,
                    classes=None if self.detect_all else self.target_classes,
                    verbose=False,
                )

            inference_time = time.time() - start_time
            self._inference_times.append(inference_time)

            # Parse results
            if results and len(results) > 0:
                result = results[0]
                boxes = result.boxes

                if boxes is not None and len(boxes) > 0:
                    for box in boxes:
                        x1, y1, x2, y2 = box.xyxy[0].cpu().numpy().astype(int)
                        conf = float(box.conf[0].cpu().numpy())
                        cls_id = int(box.cls[0].cpu().numpy())

                        class_name = self._id2name.get(cls_id, f"class_{cls_id}")

                        detection = DetectionResult(
                            bbox=(int(x1), int(y1), int(x2), int(y2)),
                            class_id=cls_id,
                            class_name=class_name,
                            confidence=conf,
                        )
                        detections.append(detection)

            self._total_detections += len(detections)

        except Exception as e:
            logger.error(f"Detection error on frame {frame_id}: {e}")

        return FrameDetections(frame_id=frame_id, camera_id=camera_id, timestamp=timestamp, detections=detections)

    def get_average_inference_time(self) -> float:
        """Get average inference time in milliseconds."""
        if not self._inference_times:
            return 0.0
        recent = list(self._inference_times)[-100:]
        return (sum(recent) / len(recent)) * 1000

    def get_fps(self) -> float:
        """Get approximate detection FPS."""
        avg_ms = self.get_average_inference_time()
        return 1000.0 / avg_ms if avg_ms > 0 else 0.0

    @staticmethod
    def draw_detections(
        frame: np.ndarray, frame_detections: FrameDetections, show_confidence: bool = True
    ) -> np.ndarray:
        """Draw bounding boxes and labels on frame."""
        annotated = frame.copy()

        colors = {
            "person": (0, 255, 0),  # Green
            "car": (255, 165, 0),  # Orange
            "motorcycle": (255, 255, 0),  # Yellow
            "bus": (0, 165, 255),  # Orange-blue
            "truck": (0, 0, 255),  # Red
            "bicycle": (255, 0, 255),  # Magenta
        }

        for det in frame_detections.detections:
            x1, y1, x2, y2 = det.bbox
            color = colors.get(det.class_name, (128, 128, 128))

            # Bounding box
            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)

            # Label
            label = det.class_name
            if show_confidence:
                label += f" {det.confidence:.2f}"

            (label_w, label_h), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
            cv2.rectangle(annotated, (x1, y1 - label_h - 8), (x1 + label_w, y1), color, -1)
            cv2.putText(annotated, label, (x1, y1 - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

        return annotated
