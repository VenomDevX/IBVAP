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

    Supports TensorRT `.engine` files for drastically faster GPU inference.
    Engine discovery priority: explicit engine_path → auto-discover .engine
    next to .pt → fall back to .pt.
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
        class_thresholds: dict[str, float] | None = None,
        half_precision: bool = True,
        fallback_model_path: str | None = None,
        engine_path: str | None = None,
    ):
        self.confidence_threshold = confidence_threshold
        self.nms_threshold = nms_threshold
        self.target_classes = target_classes or [0, 2, 3, 5, 7]
        self.detect_all = detect_all
        self.imgsz = imgsz
        self.class_thresholds = {
            _normalize_class(name): float(value)
            for name, value in (class_thresholds or {}).items()
        }
        self.inference_confidence = min(
            [self.confidence_threshold, *self.class_thresholds.values()]
        )
        self.half_precision = bool(half_precision)
        self._fallback_model_path = fallback_model_path
        self._fallback_model = None
        self._fallback_id2name: dict[int, str] = {}
        self._model = None
        self._device = device
        self._model_path = model_path
        self._engine_path = engine_path
        # A single detector is shared by all camera threads. Serial inference
        # avoids overlapping CUDA/CPU allocations and predictor races.
        self._inference_lock = threading.Lock()
        # id -> canonical class name; populated from the model after load
        self._id2name: dict[int, str] = {k: _normalize_class(v) for k, v in COCO_TARGET_CLASSES.items()}

        # Performance tracking
        self._inference_times = deque(maxlen=200)
        self._queue_wait_times = deque(maxlen=200)
        self._service_times = deque(maxlen=200)
        self._total_detections: int = 0

        self._load_model()

    @staticmethod
    def _resolve_engine_path(model_path: str, engine_path: str | None) -> str:
        """Resolve the best available model file.

        Priority:
        1. Explicit *engine_path* if the file exists.
        2. An ``.engine`` file next to *model_path* (auto-discovery).
        3. *model_path* itself (.pt fallback).
        """
        from pathlib import Path

        # 1. Explicit engine_path
        if engine_path:
            ep = Path(engine_path)
            if ep.exists():
                logger.info(f"Using explicit TensorRT engine: {ep}")
                return str(ep)
            logger.warning(f"engine_path configured but not found: {ep} — trying auto-discovery")

        # 2. Auto-discover .engine next to .pt
        mp = Path(model_path)
        if mp.suffix in (".pt", ".pth"):
            sibling_engine = mp.with_suffix(".engine")
            if sibling_engine.exists():
                logger.info(f"Auto-discovered TensorRT engine: {sibling_engine}")
                return str(sibling_engine)

        # 3. Fallback to original .pt
        return model_path

    def _load_model(self):
        """Load the YOLO model (TensorRT engine preferred, .pt fallback)."""
        if YOLO is None:
            logger.warning("YOLO not available — running in mock mode")
            return

        try:
            # Resolve best available model format
            resolved_path = self._resolve_engine_path(self._model_path, self._engine_path)
            is_engine = resolved_path.endswith(".engine")

            if is_engine:
                logger.info(f"Loading TensorRT engine: {resolved_path}")
            else:
                logger.info(f"Loading PyTorch model: {resolved_path}")

            self._model = YOLO(resolved_path)

            import torch
            # Auto-detect device, or enforce an explicitly requested GPU.
            if self._device == "auto":
                self._device = "cuda" if torch.cuda.is_available() else "cpu"
            if str(self._device).startswith("cuda"):
                if not torch.cuda.is_available():
                    raise RuntimeError(f"CUDA requested ({self._device}) but PyTorch cannot access it")
                torch.backends.cudnn.benchmark = True
                torch.backends.cuda.matmul.allow_tf32 = True

            # Prefer the model's own class names (custom coarse model)
            model_names = getattr(self._model, "names", None)

            # TensorRT engines built outside Ultralytics don't carry class
            # name metadata — names will be generic like {0: "class0", 1: "class1"}.
            # Detect this and load names from the original .pt weights.
            names_are_generic = model_names and all(
                str(v).strip() in (str(k), f"class{k}")
                for k, v in dict(model_names).items()
            )

            if is_engine and names_are_generic:
                logger.info("Engine has generic class names — loading from original .pt weights")
                try:
                    pt_model = YOLO(self._model_path)
                    pt_names = getattr(pt_model, "names", None)
                    if pt_names:
                        self._id2name = {int(k): _normalize_class(v) for k, v in dict(pt_names).items()}
                        logger.info(f"Loaded {len(self._id2name)} class names from {self._model_path}")
                    del pt_model
                except Exception as name_err:
                    logger.warning(f"Could not load class names from .pt: {name_err}")
            elif model_names and not names_are_generic:
                self._id2name = {int(k): _normalize_class(v) for k, v in dict(model_names).items()}

            if self._fallback_model_path and self._fallback_model_path != self._model_path:
                try:
                    self._fallback_model = YOLO(self._fallback_model_path)
                    fallback_names = getattr(self._fallback_model, "names", None) or COCO_TARGET_CLASSES
                    self._fallback_id2name = {
                        int(k): _normalize_class(v) for k, v in dict(fallback_names).items()
                    }
                    logger.info(f"Loaded empty-frame fallback detector: {self._fallback_model_path}")
                except Exception as fallback_error:
                    self._fallback_model = None
                    logger.warning(f"Fallback detector unavailable: {fallback_error}")

            model_desc = "TensorRT engine" if is_engine else "PyTorch model"
            logger.success(
                f"Detection {model_desc} loaded on {self._device} ({len(self._id2name)} classes, detect_all={self.detect_all})"
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
            service_started = time.perf_counter()

            # Run inference
            queue_started = time.perf_counter()
            with self._inference_lock:
                inference_started = time.perf_counter()
                results = self._model(
                    frame,
                    conf=self.inference_confidence,
                    iou=self.nms_threshold,
                    imgsz=self.imgsz,
                    device=self._device,
                    half=self.half_precision and str(self._device).startswith("cuda"),
                    classes=None if self.detect_all else self.target_classes,
                    verbose=False,
                )
                inference_seconds = time.perf_counter() - inference_started
            self._queue_wait_times.append(inference_started - queue_started)

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
                        class_floor = self.class_thresholds.get(class_name, self.confidence_threshold)
                        if conf < class_floor:
                            continue

                        detection = DetectionResult(
                            bbox=(int(x1), int(y1), int(x2), int(y2)),
                            class_id=cls_id,
                            class_name=class_name,
                            confidence=conf,
                        )
                        detections.append(detection)

            # The custom border model owns the primary taxonomy. A lightweight
            # COCO fallback is invoked only when it returns nothing, improving
            # recall on domain-shifted traffic/crowd clips without doubling the
            # cost of every frame.
            if not detections and self._fallback_model is not None:
                queue_started = time.perf_counter()
                with self._inference_lock:
                    fallback_started = time.perf_counter()
                    fallback_results = self._fallback_model(
                        frame,
                        conf=self.inference_confidence,
                        iou=self.nms_threshold,
                        imgsz=self.imgsz,
                        device=self._device,
                        half=self.half_precision and str(self._device).startswith("cuda"),
                        classes=self.target_classes,
                        verbose=False,
                    )
                    inference_seconds += time.perf_counter() - fallback_started
                self._queue_wait_times.append(fallback_started - queue_started)
                if fallback_results:
                    fallback_boxes = fallback_results[0].boxes
                    if fallback_boxes is not None:
                        for box in fallback_boxes:
                            x1, y1, x2, y2 = box.xyxy[0].cpu().numpy().astype(int)
                            conf = float(box.conf[0].cpu().numpy())
                            cls_id = int(box.cls[0].cpu().numpy())
                            class_name = self._fallback_id2name.get(cls_id, f"class_{cls_id}")
                            if conf < self.class_thresholds.get(class_name, self.confidence_threshold):
                                continue
                            detections.append(DetectionResult(
                                bbox=(int(x1), int(y1), int(x2), int(y2)),
                                class_id=cls_id,
                                class_name=class_name,
                                confidence=conf,
                            ))

            self._inference_times.append(inference_seconds)
            self._service_times.append(time.perf_counter() - service_started)
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

    def get_average_queue_wait_time(self) -> float:
        """Get recent average time waiting for the shared GPU, in milliseconds."""
        if not self._queue_wait_times:
            return 0.0
        recent = list(self._queue_wait_times)[-100:]
        return (sum(recent) / len(recent)) * 1000

    def get_average_service_time(self) -> float:
        """Get recent end-to-end detector call latency, in milliseconds."""
        if not self._service_times:
            return 0.0
        recent = list(self._service_times)[-100:]
        return (sum(recent) / len(recent)) * 1000

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
