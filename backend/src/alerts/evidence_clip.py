"""Compressed pre/post-event frame ring buffer."""

import os
import shutil
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import cv2
import numpy as np
from loguru import logger


class _ClipStore:
    """Byte count of the clips in one directory, shared by every camera writing there."""

    def __init__(self, directory: Path):
        self.lock = threading.Lock()
        self.bytes = sum(
            entry.stat().st_size
            for entry in os.scandir(directory)
            if entry.is_file() and entry.name.lower().endswith(".avi")
        )


class EvidenceClipBuffer:
    _writers = ThreadPoolExecutor(max_workers=2, thread_name_prefix="ibvap-evidence")
    _stores: dict[str, _ClipStore] = {}
    _stores_lock = threading.Lock()

    def __init__(
        self, camera_id: str, output_dir: str | Path, pre_seconds: float = 3,
        post_seconds: float = 3, capture_fps: float = 5, max_width: int = 960,
        jpeg_quality: int = 65, on_complete=None,
        max_clips_per_hour: int = 60, max_storage_mb: float = 4096, min_free_mb: float = 1024,
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
        # Budgets, like the snapshot ones in AlertEngine: an unbounded clip per
        # event once filled the disk (~1.6 MB per clip, hundreds per minute).
        self.max_clips_per_hour = max(0, int(max_clips_per_hour))
        self.max_storage_bytes = max(0.0, float(max_storage_mb)) * 1024 * 1024
        self.min_free_bytes = max(0.0, float(min_free_mb)) * 1024 * 1024
        self._clip_times: deque[float] = deque()
        self._last_warning = 0.0
        key = str(self.output_dir.resolve())
        with self._stores_lock:
            if key not in self._stores:
                self._stores[key] = _ClipStore(self.output_dir)
            self._store = self._stores[key]

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

    @classmethod
    def refresh_store(cls, directory) -> None:
        """Re-measure a clip directory after files were deleted outside the writer."""
        key = str(Path(directory).resolve())
        with cls._stores_lock:
            store = cls._stores.get(key)
        if store is not None:
            fresh = _ClipStore(Path(directory))
            with store.lock:
                store.bytes = fresh.bytes

    def trigger(self, event_id: str, timestamp: float | None = None) -> bool:
        """Start recording a clip for event_id. Returns False if a budget refused it."""
        now = time.time() if timestamp is None else timestamp
        with self._lock:
            if event_id in self._pending:
                return True
            reason = self._budget_refusal(time.time())
            if reason:
                if time.time() - self._last_warning >= 60:
                    logger.warning("Evidence clips paused camera={}: {}", self.camera_id, reason)
                    self._last_warning = time.time()
                return False
            self._clip_times.append(time.time())
            self._pending[event_id] = {"end_at": now + self.post_seconds, "frames": list(self._frames)}
            return True

    def _budget_refusal(self, now: float) -> str | None:
        while self._clip_times and now - self._clip_times[0] >= 3600:
            self._clip_times.popleft()
        if len(self._clip_times) >= self.max_clips_per_hour:
            return "hourly clip budget reached"
        with self._store.lock:
            if self._store.bytes >= self.max_storage_bytes:
                return "clip storage budget reached"
        if shutil.disk_usage(self.output_dir).free < self.min_free_bytes:
            return "minimum free disk reserve reached"
        return None

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
        with self._store.lock:
            self._store.bytes += final_path.stat().st_size
        if self.on_complete:
            try:
                self.on_complete(event_id, str(final_path))
            except Exception as exc:
                logger.error("Evidence clip callback failed event_id={} error={}", event_id, type(exc).__name__)
