"""Compressed pre/post-event frame ring buffer."""

import os
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import cv2
import numpy as np
from loguru import logger


class EvidenceClipBuffer:
    _writers = ThreadPoolExecutor(max_workers=2, thread_name_prefix="ibvap-evidence")

    def __init__(
        self, camera_id: str, output_dir: str | Path, pre_seconds: float = 3,
        post_seconds: float = 3, capture_fps: float = 5, max_width: int = 960,
        jpeg_quality: int = 65, on_complete=None,
    ):
        self.camera_id = camera_id
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.pre_seconds = max(0.0, float(pre_seconds))
        self.post_seconds = max(0.0, float(post_seconds))
        self.capture_fps = max(1.0, float(capture_fps))
        self.max_width = max(320, int(max_width))
        self.jpeg_quality = max(40, min(int(jpeg_quality), 90))
        self.on_complete = on_complete
        self._frames = deque(maxlen=max(1, int((self.pre_seconds + 1) * self.capture_fps)))
        self._pending: dict[str, dict] = {}
        self._last_sample = 0.0
        self._lock = threading.RLock()

    def add_frame(self, frame: np.ndarray, timestamp: float | None = None) -> None:
        now = time.time() if timestamp is None else timestamp
        if now - self._last_sample < 1.0 / self.capture_fps:
            return
        if frame.shape[1] > self.max_width:
            height = max(1, round(frame.shape[0] * self.max_width / frame.shape[1]))
            frame = cv2.resize(frame, (self.max_width, height), interpolation=cv2.INTER_AREA)
        ok, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, self.jpeg_quality])
        if not ok:
            return
        packet = (now, encoded.tobytes())
        completed = []
        with self._lock:
            self._last_sample = now
            self._frames.append(packet)
            cutoff = now - self.pre_seconds
            while self._frames and self._frames[0][0] < cutoff:
                self._frames.popleft()
            for event_id, capture in self._pending.items():
                capture["frames"].append(packet)
                if now >= capture["end_at"]:
                    completed.append(event_id)
            for event_id in completed:
                capture = self._pending.pop(event_id)
                self._writers.submit(self._write, event_id, capture["frames"])

    def trigger(self, event_id: str, timestamp: float | None = None) -> None:
        now = time.time() if timestamp is None else timestamp
        with self._lock:
            if event_id in self._pending:
                return
            self._pending[event_id] = {"end_at": now + self.post_seconds, "frames": list(self._frames)}

    def _write(self, event_id: str, packets: list[tuple[float, bytes]]) -> None:
        if not packets:
            return
        frames = [cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR) for _, data in packets]
        frames = [frame for frame in frames if frame is not None]
        if not frames:
            return
        height, width = frames[0].shape[:2]
        safe_event = "".join(ch for ch in event_id if ch.isalnum() or ch in "_-")
        final_path = self.output_dir / f"{self.camera_id}_{safe_event}.avi"
        temporary = final_path.with_suffix(".tmp.avi")
        writer = cv2.VideoWriter(str(temporary), cv2.VideoWriter_fourcc(*"MJPG"), self.capture_fps, (width, height))
        try:
            if not writer.isOpened():
                raise OSError("video writer unavailable")
            for frame in frames:
                if frame.shape[:2] != (height, width):
                    frame = cv2.resize(frame, (width, height))
                writer.write(frame)
        except Exception as exc:
            logger.error("Evidence clip write failed event_id={} error={}", event_id, type(exc).__name__)
            return
        finally:
            writer.release()
        os.replace(temporary, final_path)
        if self.on_complete:
            try:
                self.on_complete(event_id, str(final_path))
            except Exception as exc:
                logger.error("Evidence clip callback failed event_id={} error={}", event_id, type(exc).__name__)
