"""
IBVAP — Frame Buffer
Thread-safe frame buffer for decoupling video capture from processing.
"""

import threading
from collections import deque
from dataclasses import dataclass

import numpy as np


@dataclass
class FramePacket:
    """A single frame with metadata."""

    frame: np.ndarray
    frame_id: int
    camera_id: str
    timestamp: float
    width: int
    height: int


class FrameBuffer:
    """
    Thread-safe circular buffer for video frames.
    Drops oldest frames when capacity is reached to prevent memory buildup.
    """

    def __init__(self, max_size: int = 30):
        self._buffer: deque[FramePacket] = deque(maxlen=max_size)
        self._lock = threading.Lock()
        self._event = threading.Event()
        self._dropped_count: int = 0

    def put(self, packet: FramePacket):
        """Add a frame to the buffer. Drops oldest if full."""
        with self._lock:
            if len(self._buffer) == self._buffer.maxlen:
                self._dropped_count += 1
            self._buffer.append(packet)
            self._event.set()

    def get(self, timeout: float = 1.0) -> FramePacket | None:
        """
        Get the next frame from the buffer.
        Blocks until a frame is available or timeout is reached.
        """
        if not self._event.wait(timeout=timeout):
            return None

        with self._lock:
            if len(self._buffer) == 0:
                self._event.clear()
                return None
            packet = self._buffer.popleft()
            if len(self._buffer) == 0:
                self._event.clear()
            return packet

    def get_latest(self) -> FramePacket | None:
        """Get the most recent frame, discarding older ones."""
        with self._lock:
            if len(self._buffer) == 0:
                return None
            packet = self._buffer[-1]
            self._buffer.clear()
            self._event.clear()
            return packet

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._buffer)

    @property
    def dropped_count(self) -> int:
        return self._dropped_count

    def clear(self):
        with self._lock:
            self._buffer.clear()
            self._event.clear()

    @property
    def is_empty(self) -> bool:
        with self._lock:
            return len(self._buffer) == 0
