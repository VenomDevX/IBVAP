"""
IBVAP — Video Source Handler
Handles RTSP streams and video file input with reconnection logic.
"""

import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

import cv2
from loguru import logger


class CameraStatus(Enum):
    """Camera connection status."""

    ONLINE = "online"
    OFFLINE = "offline"
    CONNECTING = "connecting"
    ERROR = "error"
    STOPPED = "stopped"


@dataclass
class CameraInfo:
    """Camera metadata and configuration."""

    camera_id: str
    name: str
    source: str
    camera_type: str = "general"
    enabled: bool = True
    fps_limit: int = 15
    resolution: tuple[int, int] | None = None


class VideoSource:
    """
    Thread-safe video source that handles RTSP streams and video files.
    Provides reconnection logic for stream interruptions.

    Two rates: `fps_limit` is how often the pipeline analyses frames. While at
    least one person is watching the live view (`add_viewer`), every frame is
    decoded and kept at the source's own rate (up to MAX_DISPLAY_FPS) so playback
    is smooth; with no viewers, decoding drops back to the analysis rate to save CPU.
    """

    MAX_DISPLAY_FPS = 60.0

    def __init__(self, camera_info: CameraInfo, reconnect_delay: float = 5.0, max_reconnect_attempts: int = 10):
        self.camera_info = camera_info
        self.reconnect_delay = reconnect_delay
        self.max_reconnect_attempts = max_reconnect_attempts

        self._cap: cv2.VideoCapture | None = None
        self._status = CameraStatus.OFFLINE
        self._lock = threading.Lock()  # guards the latest-frame slot and status
        # Guards the capture device. Separate from _lock so a 4K decode (~20 ms)
        # never blocks readers of the latest frame (live view, analysis).
        self._cap_lock = threading.Lock()
        self._running = False
        self._frame: Any | None = None
        self._frame_id: int = 0
        self._fps: float = 0.0
        self._last_frame_time: float = 0.0
        self._reconnect_count: int = 0
        self._source_fps: float = 30.0
        self._source_width: int = 0
        self._source_height: int = 0
        self._is_file: bool = False
        self._reader_thread: threading.Thread | None = None
        self._reader_stop = threading.Event()
        self._viewers = 0
        self._viewers_lock = threading.Lock()

    @property
    def status(self) -> CameraStatus:
        return self._status

    @property
    def frame_id(self) -> int:
        return self._frame_id

    @property
    def fps(self) -> float:
        return self._fps

    @property
    def last_frame_at(self) -> float | None:
        return self._last_frame_time or None

    @property
    def is_capturing(self) -> bool:
        """True while the background capture thread is running."""
        reader = self._reader_thread
        return self._running and reader is not None and reader.is_alive()

    @property
    def source_resolution(self) -> tuple[int, int]:
        return (self._source_width, self._source_height)

    @property
    def display_active(self) -> bool:
        return self._viewers > 0

    def add_viewer(self) -> None:
        with self._viewers_lock:
            self._viewers += 1

    def remove_viewer(self) -> None:
        with self._viewers_lock:
            self._viewers = max(0, self._viewers - 1)

    def latest(self) -> tuple[int, Any | None, float]:
        """(frame_id, frame, capture time) of the newest frame, read atomically."""
        with self._lock:
            return self._frame_id, self._frame, self._last_frame_time

    def connect(self) -> bool:
        """Establish connection to video source."""
        self._status = CameraStatus.CONNECTING
        logger.info(f"[{self.camera_info.camera_id}] Connecting to: {self.camera_info.source}")

        try:
            source = self.camera_info.source

            # Determine if RTSP or file
            if source.startswith("rtsp://") or source.startswith("http://"):
                self._is_file = False
                self._cap = cv2.VideoCapture(source, cv2.CAP_FFMPEG)
                # Set buffer size for RTSP to reduce latency
                self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            else:
                self._is_file = True
                self._cap = cv2.VideoCapture(source)

            if not self._cap.isOpened():
                logger.error(f"[{self.camera_info.camera_id}] Failed to open source")
                self._status = CameraStatus.ERROR
                return False

            # Get source properties
            self._source_fps = self._cap.get(cv2.CAP_PROP_FPS) or 30.0
            self._source_width = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            self._source_height = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

            # Prime one frame synchronously so consumers do not see an empty
            # source while the latest-frame capture worker starts.
            ret, frame = self._cap.read()
            if not ret or frame is None:
                logger.error(f"[{self.camera_info.camera_id}] Source opened but produced no frame")
                self._cap.release()
                self._cap = None
                self._status = CameraStatus.ERROR
                return False
            with self._lock:
                self._store_frame(frame, time.time())

            self._status = CameraStatus.ONLINE
            self._reconnect_count = 0
            self._running = True
            self._reader_stop.clear()
            self._reader_thread = threading.Thread(
                target=self._reader_loop,
                name=f"ibvap-capture-{self.camera_info.camera_id}",
                daemon=True,
            )
            self._reader_thread.start()
            logger.success(
                f"[{self.camera_info.camera_id}] Connected — "
                f"{self._source_width}x{self._source_height} @ {self._source_fps:.1f} FPS"
            )
            return True

        except Exception as e:
            logger.error(f"[{self.camera_info.camera_id}] Connection error: {e}")
            self._status = CameraStatus.ERROR
            return False

    def read_frame(self) -> tuple[bool, Any | None]:
        """
        Read a single frame from the video source.
        Returns (success, frame) tuple.
        Thread-safe.
        """
        with self._lock:
            # Capture is performed by the background latest-frame worker.
            # Returning this slot prevents inference latency from creating a
            # growing decoder backlog.
            if self._frame is not None:
                if self._status in {CameraStatus.ERROR, CameraStatus.OFFLINE}:
                    return False, None
                return True, self._frame
            if self._cap is None or not self._cap.isOpened():
                return False, None

            # FPS limiting
            if self.camera_info.fps_limit > 0:
                min_interval = 1.0 / self.camera_info.fps_limit
                elapsed = time.time() - self._last_frame_time
                if elapsed < min_interval:
                    return True, self._frame  # Return last frame

            with self._cap_lock:
                ret, frame = self._cap.read()

            if not ret:
                # A file source that ran out of frames is not an error — loop it
                # (the demo cameras are looping clips). Only a live stream that
                # stops delivering frames is a genuine fault.
                if self._is_file:
                    with self._cap_lock:
                        self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                        ret, frame = self._cap.read()
                if not ret:
                    self._status = CameraStatus.ERROR if not self._is_file else CameraStatus.OFFLINE
                    return False, None

            # Resize if configured
            if self.camera_info.resolution:
                w, h = self.camera_info.resolution
                frame = cv2.resize(frame, (w, h))

            # Update state
            now = time.time()
            if self._last_frame_time > 0:
                dt = now - self._last_frame_time
                self._fps = 1.0 / dt if dt > 0 else 0.0
            self._last_frame_time = now
            self._frame = frame
            self._frame_id += 1
            if self._status != CameraStatus.ONLINE:
                self._status = CameraStatus.ONLINE

            return True, frame

    def _store_frame(self, frame, now: float) -> None:
        if self.camera_info.resolution:
            width, height = self.camera_info.resolution
            if frame.shape[1] != width or frame.shape[0] != height:
                frame = cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)
        if self._last_frame_time > 0:
            elapsed = now - self._last_frame_time
            self._fps = 1.0 / elapsed if elapsed > 0 else 0.0
        self._last_frame_time = now
        self._frame = frame
        self._frame_id += 1
        self._status = CameraStatus.ONLINE

    def _reader_loop(self) -> None:
        """Capture continuously and drop superseded frames instead of queueing them."""
        # With nobody watching, demo files do not need decoding at 30/60 FPS when
        # analysis is capped lower: pacing decoding to the analysis rate avoids
        # wasting a CPU core per 4K source. While someone watches, every frame is
        # kept so playback runs at the source's own rate.
        source_fps = min(self._source_fps or 30.0, self.MAX_DISPLAY_FPS)
        analysis_fps = float(self.camera_info.fps_limit) if self.camera_info.fps_limit > 0 else source_fps
        idle_output_interval = 1.0 / max(analysis_fps, 1.0) if self.camera_info.fps_limit > 0 else 0.0
        last_stored = self._last_frame_time
        next_due = time.perf_counter()
        try:
            while self._running and not self._reader_stop.is_set():
                viewing = self.display_active
                decode_fps = source_fps if viewing else min(source_fps, analysis_fps)
                source_interval = 1.0 / max(decode_fps, 1.0) if self._is_file else 0.0
                output_interval = 0.0 if viewing else idle_output_interval
                with self._cap_lock:
                    capture = self._cap
                    if capture is None or not capture.isOpened():
                        break
                    ret, frame = capture.read()
                    if (not ret or frame is None) and self._is_file:
                        capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
                        ret, frame = capture.read()

                if not ret or frame is None:
                    self._status = CameraStatus.ERROR if not self._is_file else CameraStatus.OFFLINE
                    break

                now = time.time()
                if output_interval == 0.0 or now - last_stored >= output_interval * 0.9:
                    with self._lock:
                        self._store_frame(frame, now)
                    last_stored = now

                if source_interval:
                    # Pace against a running schedule, not "sleep what is left of
                    # this frame": Windows sleeps round up to ~15.6 ms, which turned
                    # a 33 ms frame budget into ~46 ms (30 FPS files played at ~21).
                    # An oversleep here is made up by skipping the next wait.
                    next_due += source_interval
                    remaining = next_due - time.perf_counter()
                    if remaining > 0:
                        self._reader_stop.wait(remaining)
                    elif remaining < -source_interval:
                        next_due = time.perf_counter()  # fell far behind: resync, don't burst
        except Exception as exc:
            # Without this the thread dies silently (e.g. OpenCV out of memory)
            # while the camera keeps reporting ONLINE with a frozen last frame.
            logger.error(f"[{self.camera_info.camera_id}] Capture thread failed: {exc!r}")
            self._status = CameraStatus.ERROR
        finally:
            self._running = False

    def reconnect(self, stop_event: threading.Event | None = None) -> bool:
        """Attempt to reconnect to the video source."""
        if self._reconnect_count >= self.max_reconnect_attempts:
            logger.error(
                f"[{self.camera_info.camera_id}] Max reconnect attempts ({self.max_reconnect_attempts}) reached"
            )
            self._status = CameraStatus.OFFLINE
            return False

        self._reconnect_count += 1
        logger.warning(
            f"[{self.camera_info.camera_id}] Reconnect attempt {self._reconnect_count}/{self.max_reconnect_attempts}"
        )

        self.release()
        if stop_event is not None:
            if stop_event.wait(self.reconnect_delay):
                return False
        else:
            time.sleep(self.reconnect_delay)
        return self.connect()

    def release(self):
        """Release the video capture resource."""
        self._running = False
        self._reader_stop.set()
        reader = self._reader_thread
        with self._cap_lock:
            if self._cap is not None:
                self._cap.release()
                self._cap = None
        with self._lock:
            self._frame = None
            self._status = CameraStatus.STOPPED
        if reader is not None and reader is not threading.current_thread():
            reader.join(timeout=2)
        # A reader may have been inside _store_frame when shutdown began.
        # Reassert terminal state after joining so status cannot race back online.
        with self._lock:
            self._frame = None
            self._status = CameraStatus.STOPPED
        self._reader_thread = None

    def is_stream(self) -> bool:
        """Check if the source is a live stream (RTSP/HTTP) vs a file."""
        src = self.camera_info.source
        return src.startswith("rtsp://") or src.startswith("http://")

    def get_total_frames(self) -> int:
        """Get total frame count for video files. Returns -1 for streams."""
        if self.is_stream():
            return -1
        if self._cap is not None:
            return int(self._cap.get(cv2.CAP_PROP_FRAME_COUNT))
        return -1

    def get_status_dict(self) -> dict:
        """Return a JSON-serializable status dictionary."""
        return {
            "camera_id": self.camera_info.camera_id,
            "name": self.camera_info.name,
            "source": self.camera_info.source,
            "type": self.camera_info.camera_type,
            "status": self._status.value,
            "fps": round(self._fps, 1),
            "resolution": f"{self._source_width}x{self._source_height}",
            "frame_id": self._frame_id,
            "enabled": self.camera_info.enabled,
        }
