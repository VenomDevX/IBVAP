"""
IBVAP — Loitering Detector
Identifies objects dwelling in a zone beyond configured thresholds.
"""

import time
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from loguru import logger

from src.tracking.track import Track


@dataclass
class LoiteringEvent:
    """A detected loitering event."""
    track_id: int
    camera_id: str
    zone_id: str
    duration: float  # seconds
    average_speed: float
    position_variance: float
    start_time: float
    detected_at: float


class LoiteringDetector:
    """
    Detects loitering behavior based on:
    - Zone occupancy duration
    - Movement distance
    - Average speed
    - Position variance (staying near same spot)
    """

    def __init__(
        self,
        threshold_seconds: float = 30.0,
        min_movement_pixels: float = 50.0,
        stationary_speed_threshold: float = 5.0,
    ):
        self.threshold_seconds = threshold_seconds
        self.min_movement = min_movement_pixels
        self.stationary_speed = stationary_speed_threshold

        # Track zone entry times: (track_id, zone_id) -> entry_time
        self._zone_occupancy: Dict[Tuple[int, str], float] = {}
        # Track IDs already flagged as loitering (to avoid duplicate events)
        self._flagged: Dict[Tuple[int, str], float] = {}

    def check_loitering(self, track: Track, current_zones: List[str]) -> List[LoiteringEvent]:
        """
        Check if a track is loitering in any of its current zones.

        Args:
            track: The tracked object
            current_zones: List of zone IDs the track is currently inside

        Returns:
            List of loitering events (usually 0 or 1)
        """
        events = []
        now = time.time()

        # Update zone occupancy
        for zone_id in current_zones:
            key = (track.track_id, zone_id)

            if key not in self._zone_occupancy:
                self._zone_occupancy[key] = now
                continue

            entry_time = self._zone_occupancy[key]
            duration = now - entry_time

            # Check if loitering threshold exceeded
            if duration >= self.threshold_seconds:
                # Check if not already flagged (or re-flag after cooldown)
                if key not in self._flagged or (now - self._flagged[key]) > 120:
                    # Calculate position variance
                    variance = self._calculate_position_variance(track)

                    event = LoiteringEvent(
                        track_id=track.track_id,
                        camera_id=track.camera_id,
                        zone_id=zone_id,
                        duration=duration,
                        average_speed=track.average_speed,
                        position_variance=variance,
                        start_time=entry_time,
                        detected_at=now,
                    )

                    events.append(event)
                    self._flagged[key] = now
                    track.is_loitering = True

                    logger.info(
                        f"Loitering detected: Track {track.track_id} in zone "
                        f"{zone_id} for {duration:.1f}s"
                    )

        # Clean up zones the track has left
        keys_to_remove = []
        for key in self._zone_occupancy:
            tid, zid = key
            if tid == track.track_id and zid not in current_zones:
                keys_to_remove.append(key)

        for key in keys_to_remove:
            del self._zone_occupancy[key]

        return events

    def _calculate_position_variance(self, track: Track) -> float:
        """
        Calculate spatial variance of recent trajectory points.
        Low variance = staying in same spot = more suspicious loitering.
        """
        recent = track.get_recent_trajectory(30)
        if len(recent) < 2:
            return 0.0

        xs = [p[0] for p in recent]
        ys = [p[1] for p in recent]

        import numpy as np
        var_x = np.var(xs)
        var_y = np.var(ys)

        return float(var_x + var_y)

    def get_zone_duration(self, track_id: int, zone_id: str) -> float:
        """Get how long a track has been in a zone."""
        key = (track_id, zone_id)
        if key in self._zone_occupancy:
            return time.time() - self._zone_occupancy[key]
        return 0.0

    def reset(self):
        self._zone_occupancy.clear()
        self._flagged.clear()
