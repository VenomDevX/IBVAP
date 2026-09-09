"""
IBVAP — Video Source Handler
Handles RTSP streams and video file input with reconnection logic.
"""

import cv2
import time
import threading
from typing import Optional, Tuple
from dataclasses import dataclass
from enum import Enum
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
    resolution: Optional[Tuple[int, int]] = None


class VideoSource:
    """
    Thread-safe video source that handles RTSP streams and video files.
    Provides reconnection logic for stream interruptions.
    """

    def __init__(self, camera_info: CameraInfo, reconnect_delay: float = 5.0,
                 max_reconnect_attempts: int = 10):
        self.camera_info = camera_info
        self.reconnect_delay = reconnect_delay
        self.max_reconnect_attempts = max_reconnect_attempts

        self._cap: Optional[cv2.VideoCapture] = None
        self._status = CameraStatus.OFFLINE
        self._lock = threading.Lock()
        self._running = False
        self._frame: Optional[any] = None
        self._frame_id: int = 0
        self._fps: float = 0.0
        self._last_frame_time: float = 0.0
        self._reconnect_count: int = 0
        self._source_fps: float = 30.0
        self._source_width: int = 0
        self._source_height: int = 0
        self._is_file: bool = False

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
    def source_resolution(self) -> Tuple[int, int]:
        return (self._source_width, self._source_height)

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

            self._status = CameraStatus.ONLINE
            self._reconnect_count = 0
            logger.success(
                f"[{self.camera_info.camera_id}] Connected — "
                f"{self._source_width}x{self._source_height} @ {self._source_fps:.1f} FPS"
            )
            return True

        except Exception as e:
            logger.error(f"[{self.camera_info.camera_id}] Connection error: {e}")
            self._status = CameraStatus.ERROR
            return False

    def read_frame(self) -> Tuple[bool, Optional[any]]:
        """
        Read a single frame from the video source.
        Returns (success, frame) tuple.
        Thread-safe.
        """
        with self._lock:
            if self._cap is None or not self._cap.isOpened():
                return False, None

            # FPS limiting
            if self.camera_info.fps_limit > 0:
                min_interval = 1.0 / self.camera_info.fps_limit
                elapsed = time.time() - self._last_frame_time
                if elapsed < min_interval:
                    return True, self._frame  # Return last frame

            ret, frame = self._cap.read()

            if not ret:
                # A file source that ran out of frames is not an error — loop it
                # (the demo cameras are looping clips). Only a live stream that
                # stops delivering frames is a genuine fault.
                if self._is_file:
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

    def reconnect(self) -> bool:
        """Attempt to reconnect to the video source."""
        if self._reconnect_count >= self.max_reconnect_attempts:
            logger.error(
                f"[{self.camera_info.camera_id}] Max reconnect attempts "
                f"({self.max_reconnect_attempts}) reached"
            )
            self._status = CameraStatus.OFFLINE
            return False

        self._reconnect_count += 1
        logger.warning(
            f"[{self.camera_info.camera_id}] Reconnect attempt "
            f"{self._reconnect_count}/{self.max_reconnect_attempts}"
        )

        self.release()
        time.sleep(self.reconnect_delay)
        return self.connect()

    def release(self):
        """Release the video capture resource."""
        with self._lock:
            if self._cap is not None:
                self._cap.release()
                self._cap = None
            self._status = CameraStatus.STOPPED

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
