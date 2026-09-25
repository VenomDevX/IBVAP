"""Short, isolated end-to-end GPU pipeline smoke test (never trains models)."""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=float, default=15.0)
    parser.add_argument("--require-face", action="store_true")
    parser.add_argument("--output", default=str(BACKEND / "outputs" / "metrics" / "runtime_smoke.json"))
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="ibvap-smoke-") as temporary:
        temp = Path(temporary)
        os.environ["DATABASE_URL"] = f"sqlite:///{(temp / 'smoke.db').as_posix()}"
        os.environ["IBVAP_OUTPUT_DIR"] = str(temp / "outputs")
        os.environ["IBVAP_PERSIST_EVENTS"] = "false"

        from src.database.db import get_database
        from src.pipeline.pipeline import IBVAPPipeline

        pipeline = IBVAPPipeline()
        started = time.perf_counter()
        pipeline.initialize()
        if pipeline.detector is None or not str(pipeline.detector._device).startswith("cuda"):
            raise SystemExit("smoke failed: object detector is not using CUDA")
        face = pipeline.face_recognizer
        if args.require_face and (
            not face.active
            or face._detector.device != "cuda:0"
            or any("CUDAExecutionProvider" not in providers for providers in face._detector.providers.values())
        ):
            raise SystemExit("smoke failed: face detection/embedding is not using CUDA")

        try:
            pipeline.start_all()
            deadline = time.monotonic() + max(1.0, args.seconds)
            while time.monotonic() < deadline:
                time.sleep(0.25)
        finally:
            pipeline.stop_all()

        stats = pipeline.get_all_stats()
        healthy = {camera_id: row for camera_id, row in stats.items() if row.get("frames_processed", 0) > 0}
        report = {
            "generated_at": time.time(),
            "device": pipeline.detector._device,
            "face_active": face.active,
            "face_device": face._detector.device if face.active else "unavailable",
            "face_providers": face._detector.providers if face.active else {},
            "elapsed_seconds": round(time.perf_counter() - started, 2),
            "configured_cameras": len(stats),
            "cameras_processing": len(healthy),
            "total_frames_processed": sum(row.get("frames_processed", 0) for row in stats.values()),
            "mean_pipeline_fps": round(statistics.fmean(row.get("fps", 0.0) for row in healthy.values()), 2)
            if healthy
            else 0.0,
            "detector_mean_ms": round(pipeline.detector.get_average_inference_time(), 2),
            "detector_queue_ms": round(pipeline.detector.get_average_queue_wait_time(), 2),
            "detector_service_ms": round(pipeline.detector.get_average_service_time(), 2),
            "cameras": stats,
        }
        destination = Path(args.output)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
        get_database().close()
        if len(healthy) != len(stats):
            raise SystemExit("smoke failed: one or more configured cameras processed no frames")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
