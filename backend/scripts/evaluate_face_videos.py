"""Evaluate InsightFace detection and embedding on demo videos (never trains)."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

import cv2
import numpy as np

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from src.face.face_detector import FaceDetector  # noqa: E402


def _indices(frame_count: int, count: int) -> list[int]:
    if frame_count <= 0:
        return list(range(count))
    return sorted({int(value) for value in np.linspace(0, frame_count - 1, count)})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video-dir", default=str(BACKEND / "data" / "demo"))
    parser.add_argument("--samples", type=int, default=10)
    parser.add_argument(
        "--output",
        default=str(BACKEND / "outputs" / "metrics" / "face_video_report.json"),
    )
    args = parser.parse_args()

    detector = FaceDetector(device="cuda:0")
    if detector._model is None or detector.device != "cuda:0":
        raise SystemExit("face evaluation failed: CUDA InsightFace model is unavailable")
    if any("CUDAExecutionProvider" not in active for active in detector.providers.values()):
        raise SystemExit("face evaluation failed: an InsightFace session fell back to CPU")

    videos = sorted(Path(args.video_dir).glob("*.mp4"))
    rows: list[dict] = []
    all_times: list[float] = []
    total_faces = total_embeddings = total_frames = 0
    for video in videos:
        capture = cv2.VideoCapture(str(video))
        frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        times: list[float] = []
        confidences: list[float] = []
        faces = embeddings = sampled = frames_with_faces = 0
        if capture.isOpened():
            for index in _indices(frame_count, max(1, args.samples)):
                capture.set(cv2.CAP_PROP_POS_FRAMES, index)
                ok, frame = capture.read()
                if not ok or frame is None:
                    continue
                started = time.perf_counter()
                found = detector.detect_faces(frame)
                elapsed = (time.perf_counter() - started) * 1000
                sampled += 1
                faces += len(found)
                frames_with_faces += bool(found)
                embeddings += sum(bool(face.get("embedding")) for face in found)
                confidences.extend(float(face["confidence"]) for face in found)
                times.append(elapsed)
                all_times.append(elapsed)
        capture.release()
        total_frames += sampled
        total_faces += faces
        total_embeddings += embeddings
        rows.append(
            {
                "file": video.name,
                "opened": sampled > 0,
                "sampled_frames": sampled,
                "faces": faces,
                "embeddings": embeddings,
                "frames_with_face_rate": None if sampled == 0 else round(frames_with_faces / sampled, 4),
                "mean_face_confidence": round(statistics.fmean(confidences), 4) if confidences else None,
                "mean_inference_ms": round(statistics.fmean(times), 2) if times else None,
            }
        )

    report = {
        "schema_version": 1,
        "generated_at": time.time(),
        "device": detector.device,
        "providers": detector.providers,
        "model": "insightface/buffalo_l",
        "training_performed": False,
        "summary": {
            "videos": len(videos),
            "sampled_frames": total_frames,
            "faces": total_faces,
            "embeddings": total_embeddings,
            "mean_inference_ms": round(statistics.fmean(all_times), 2) if all_times else None,
            "p95_inference_ms": round(float(np.percentile(all_times, 95)), 2) if all_times else None,
        },
        "videos": rows,
    }
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
