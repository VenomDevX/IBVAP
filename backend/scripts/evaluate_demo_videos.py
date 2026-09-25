"""Run a repeatable detector/latency smoke test over every local demo video.

This deliberately separates two ideas:
* labelled accuracy (precision/recall/mAP) belongs to the YOLO validation set;
* unlabelled demo clips can measure coverage, confidence, class mix and latency,
  but cannot truthfully produce an accuracy percentage.

The JSON result is suitable for CI artifacts and before/after comparisons.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from collections import Counter
from pathlib import Path

import cv2
import yaml

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from src.detection.detector import ObjectDetector  # noqa: E402

VIDEO_SUFFIXES = {".mp4", ".avi", ".mov", ".mkv", ".webm", ".mpeg", ".mpg"}


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round((len(ordered) - 1) * fraction))]


def inspect_video(path: Path, detector: ObjectDetector, samples: int) -> dict:
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        return {"file": path.name, "opened": False, "error": "OpenCV could not open video"}

    frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    sample_count = min(max(1, samples), max(frame_count, 1))
    positions = sorted({round(i * max(frame_count - 1, 0) / max(sample_count - 1, 1)) for i in range(sample_count)})

    class_counts: Counter[str] = Counter()
    confidences: list[float] = []
    latencies: list[float] = []
    frames_with_detections = 0
    decoded = 0
    try:
        for sample_index, position in enumerate(positions):
            capture.set(cv2.CAP_PROP_POS_FRAMES, position)
            ok, frame = capture.read()
            if not ok or frame is None:
                continue
            decoded += 1
            started = time.perf_counter()
            result = detector.detect(frame, sample_index, path.stem)
            latencies.append((time.perf_counter() - started) * 1000.0)
            if result.detections:
                frames_with_detections += 1
            for detection in result.detections:
                class_counts[detection.class_name] += 1
                confidences.append(detection.confidence)
    finally:
        capture.release()

    return {
        "file": path.name,
        "opened": True,
        "width": width,
        "height": height,
        "source_fps": round(fps, 3),
        "frame_count": frame_count,
        "duration_seconds": round(frame_count / fps, 3) if fps > 0 else None,
        "sampled_frames": decoded,
        "frames_with_detections": frames_with_detections,
        "detection_coverage": round(frames_with_detections / decoded, 4) if decoded else 0.0,
        "detections": sum(class_counts.values()),
        "classes": dict(class_counts.most_common()),
        "mean_confidence": round(statistics.fmean(confidences), 4) if confidences else 0.0,
        "p50_inference_ms": round(percentile(latencies, 0.50), 2),
        "p95_inference_ms": round(percentile(latencies, 0.95), 2),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video-dir", default=str(BACKEND / "data" / "demo"))
    parser.add_argument("--weights", default="")
    parser.add_argument("--samples-per-video", type=int, default=20)
    parser.add_argument("--output", default=str(BACKEND / "outputs" / "metrics" / "demo_video_report.json"))
    args = parser.parse_args()

    thresholds = yaml.safe_load((BACKEND / "configs" / "thresholds.yaml").read_text(encoding="utf-8"))
    detection = thresholds.get("detection", {})
    configured = args.weights or detection.get("weights_path") or ""
    weights = Path(configured)
    if not weights.is_absolute():
        weights = BACKEND / weights
    if not weights.exists():
        raise SystemExit(f"detector weights not found: {weights}")
    fallback = detection.get("fallback_weights_path") if not args.weights else None
    fallback_path = None
    if fallback:
        fallback_path = Path(fallback)
        if not fallback_path.is_absolute():
            fallback_path = BACKEND / fallback_path
        if not fallback_path.exists():
            fallback_path = None

    videos = sorted(
        path for path in Path(args.video_dir).iterdir() if path.is_file() and path.suffix.lower() in VIDEO_SUFFIXES
    )
    if not videos:
        raise SystemExit(f"no demo videos found in {args.video_dir}")

    detector = ObjectDetector(
        model_path=str(weights),
        confidence_threshold=float(detection.get("confidence_threshold", 0.3)),
        nms_threshold=float(detection.get("nms_threshold", 0.45)),
        device=detection.get("device", "auto"),
        imgsz=int(detection.get("imgsz", 640)),
        detect_all=True,
        class_thresholds=detection.get("class_thresholds", {}),
        half_precision=bool(detection.get("half_precision", True)),
        fallback_model_path=str(fallback_path) if fallback_path else None,
    )
    if detector._model is None:
        raise SystemExit("detector model failed to load")

    started = time.perf_counter()
    rows = [inspect_video(path, detector, args.samples_per_video) for path in videos]
    opened = [row for row in rows if row.get("opened")]
    output = {
        "schema_version": 1,
        "generated_at": time.time(),
        "weights": str(weights),
        "device": detector._device,
        "accuracy": {
            "available": False,
            "reason": "Demo videos have no frame-level ground-truth boxes; use ml.eval_detector for labelled mAP.",
        },
        "summary": {
            "videos_found": len(videos),
            "videos_opened": len(opened),
            "sampled_frames": sum(row.get("sampled_frames", 0) for row in opened),
            "detections": sum(row.get("detections", 0) for row in opened),
            "wall_seconds": round(time.perf_counter() - started, 2),
            "model_mean_inference_ms": round(detector.get_average_inference_time(), 2),
        },
        "videos": rows,
    }
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(json.dumps(output["summary"], indent=2))
    print(f"report: {destination}")
    return 0 if len(opened) == len(videos) else 1


if __name__ == "__main__":
    raise SystemExit(main())
