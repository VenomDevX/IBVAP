"""
IBVAP — Batched multi-camera detection coordinator.

Each CameraPipeline runs its own thread and, before this existed, called
ObjectDetector.detect() with ONE frame at a time. With several cameras
running concurrently, that serializes the GPU into N tiny single-image
forward passes per tick instead of one batched call — under-utilizing the
GPU (kernel-launch overhead dominates, SMs idle between calls).

BatchDetectionCoordinator collects one frame per camera per tick and runs a
single ObjectDetector.detect_batch() call across all of them, then routes
each result back to the camera that submitted it. A per-call timeout falls
back to a direct single-frame detect() so one stuck camera or a coordinator
hiccup can never wedge the whole pipeline.
"""

import threading
import time

import numpy as np
from loguru import logger

from src.detection.detection_result import FrameDetections
from src.detection.detector import ObjectDetector


class _BatchFailed:
    """Sentinel result: the batch call raised, so the submitter must retry alone."""


_BATCH_FAILED = _BatchFailed()


class BatchDetectionCoordinator:
    def __init__(self, detector: ObjectDetector, tick_interval_s: float = 0.02, submit_timeout_s: float = 2.0):
        self._detector = detector
        self._tick_interval_s = tick_interval_s
        self._submit_timeout_s = submit_timeout_s

        # Every submission gets a sequence number; results are tagged with it so
        # a batch that finishes after its submitter timed out can never be handed
        # to that camera's *next* frame.
        self._cond = threading.Condition()
        self._seq = 0
        self._pending: dict[str, tuple[int, np.ndarray, float]] = {}
        self._results: dict[str, tuple[int, object]] = {}
        self._registered: set[str] = set()

        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._batch_loop, daemon=True, name="batch-detect-coordinator")
        self._thread.start()

    def register_camera(self, camera_id: str) -> None:
        with self._cond:
            self._registered.add(camera_id)

    def unregister_camera(self, camera_id: str) -> None:
        with self._cond:
            self._registered.discard(camera_id)
            self._pending.pop(camera_id, None)
            self._results.pop(camera_id, None)
            self._cond.notify_all()

    def stop(self) -> None:
        self._stop_event.set()
        self._thread.join(timeout=2)

    def submit(self, camera_id: str, frame: np.ndarray, frame_id: int = 0) -> FrameDetections:
        """Submit a frame for the next batch tick and block for its result.

        Falls back to a direct single-frame detect() if the batch result doesn't
        arrive within submit_timeout_s, or if the batch call itself failed.
        """
        captured_at = time.time()
        with self._cond:
            if camera_id not in self._registered or self._stop_event.is_set():
                seq = None
            else:
                self._seq += 1
                seq = self._seq
                self._pending[camera_id] = (seq, frame, captured_at)
                self._results.pop(camera_id, None)
                deadline = time.monotonic() + self._submit_timeout_s
                while True:
                    got = self._results.get(camera_id)
                    if got is not None and got[0] == seq:
                        del self._results[camera_id]
                        outcome = got[1]
                        break
                    remaining = deadline - time.monotonic()
                    if remaining <= 0 or camera_id not in self._registered:
                        outcome = None
                        # Withdraw the frame if the loop hasn't picked it up yet.
                        if self._pending.get(camera_id, (None,))[0] == seq:
                            del self._pending[camera_id]
                        break
                    self._cond.wait(remaining)

        if seq is not None and isinstance(outcome, list):
            return FrameDetections(frame_id=frame_id, camera_id=camera_id, timestamp=captured_at, detections=outcome)
        if seq is not None:
            reason = "batch call failed" if outcome is _BATCH_FAILED else "timeout"
            logger.warning(f"Batch detection {reason} for camera={camera_id} — falling back to single-frame detect()")
        return self._detector.detect(frame, frame_id=frame_id, camera_id=camera_id)

    def _batch_loop(self) -> None:
        while not self._stop_event.wait(self._tick_interval_s):
            with self._cond:
                if not self._pending:
                    continue
                batch = list(self._pending.items())
                self._pending.clear()

            camera_ids = [cid for cid, _ in batch]
            frames = [item[1] for _, item in batch]
            try:
                per_frame: list = list(self._detector.detect_batch(frames, camera_ids))
                if len(per_frame) != len(frames):
                    raise RuntimeError(f"detect_batch returned {len(per_frame)} results for {len(frames)} frames")
            except Exception as e:
                logger.error(f"Batch detection tick failed ({len(frames)} frames): {e}")
                per_frame = [_BATCH_FAILED] * len(frames)

            with self._cond:
                for (camera_id, (seq, _frame, _ts)), detections in zip(batch, per_frame):
                    if camera_id in self._registered:
                        self._results[camera_id] = (seq, detections)
                self._cond.notify_all()
