"""
IBVAP — Night Detector
Detects night-time or low-illumination conditions.
"""

from datetime import datetime
from datetime import time as dt_time

import cv2
import numpy as np
from loguru import logger


class NightDetector:
    """
    Detects night-time conditions using:
    1. Time-based detection (configured night hours)
    2. Frame brightness analysis (low-illumination detection)
    """

    def __init__(
        self,
        night_start: str = "19:00",
        night_end: str = "05:00",
        brightness_threshold: int = 60,
    ):
        self.night_start = self._parse_time(night_start)
        self.night_end = self._parse_time(night_end)
        self.brightness_threshold = brightness_threshold

        self._last_brightness: float = 128.0
        self._is_night_by_time: bool = False
        self._is_low_light: bool = False

    @staticmethod
    def _parse_time(time_str: str) -> dt_time:
        """Parse HH:MM time string."""
        parts = time_str.split(":")
        return dt_time(int(parts[0]), int(parts[1]))

    def is_night_time(self, timestamp: float | None = None) -> bool:
        """Check if current time falls within configured night hours."""
        if timestamp:
            dt = datetime.fromtimestamp(timestamp)
        else:
            dt = datetime.now()

        current_time = dt.time()

        # Handle overnight range (e.g., 19:00 to 05:00)
        if self.night_start > self.night_end:
            self._is_night_by_time = current_time >= self.night_start or current_time <= self.night_end
        else:
            self._is_night_by_time = self.night_start <= current_time <= self.night_end

        return self._is_night_by_time

    def is_low_light(self, frame: np.ndarray) -> bool:
        """
        Analyze frame brightness to detect low-illumination conditions.
        Uses average brightness of the grayscale image.
        """
        try:
            if len(frame.shape) == 3:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            else:
                gray = frame

            self._last_brightness = float(np.mean(gray))
            self._is_low_light = self._last_brightness < self.brightness_threshold

            return self._is_low_light

        except Exception as e:
            logger.error(f"Brightness analysis error: {e}")
            return False

    def get_night_context(self, frame: np.ndarray | None = None, timestamp: float | None = None) -> dict:
        """
        Get comprehensive night/light context.
        Combines time-based and brightness-based analysis.
        """
        night_by_time = self.is_night_time(timestamp)
        low_light = False
        brightness = self._last_brightness

        if frame is not None:
            low_light = self.is_low_light(frame)
            brightness = self._last_brightness

        return {
            "is_night_time": night_by_time,
            "is_low_light": low_light,
            "is_night": night_by_time or low_light,
            "brightness": round(brightness, 1),
            "brightness_threshold": self.brightness_threshold,
            "night_hours": f"{self.night_start.strftime('%H:%M')}-{self.night_end.strftime('%H:%M')}",
        }
