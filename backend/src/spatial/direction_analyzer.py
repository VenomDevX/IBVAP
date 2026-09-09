"""
IBVAP — Direction Analyzer
Estimates movement direction using object trajectory history.
"""

import math
from typing import Optional, Tuple
from src.tracking.track import Track


class DirectionAnalyzer:
    """
    Analyzes movement direction from trajectory history.
    Provides configurable direction classification relative to zones.
    """

    # Cardinal direction constants
    DIRECTIONS = {
        "up": (-90, "Moving upward"),
        "down": (90, "Moving downward"),
        "left": (180, "Moving left"),
        "right": (0, "Moving right"),
        "up_left": (-135, "Moving upper-left"),
        "up_right": (-45, "Moving upper-right"),
        "down_left": (135, "Moving lower-left"),
        "down_right": (45, "Moving lower-right"),
        "stationary": (None, "Stationary"),
        "unknown": (None, "Unknown"),
    }

    def __init__(self, min_trajectory_points: int = 5,
                 stationary_threshold: float = 5.0):
        """
        Args:
            min_trajectory_points: Minimum trajectory points needed for analysis
            stationary_threshold: Speed below this (px/s) = stationary
        """
        self.min_points = min_trajectory_points
        self.stationary_threshold = stationary_threshold

    def analyze_direction(self, track: Track) -> str:
        """
        Determine the primary movement direction of a track.
        Uses recent trajectory points to compute average movement vector.
        """
        recent = track.get_recent_trajectory(self.min_points * 2)
        if len(recent) < self.min_points:
            return "unknown"

        # Check if stationary
        if track.average_speed < self.stationary_threshold:
            return "stationary"

        # Calculate average direction vector from recent trajectory
        dx_total = 0.0
        dy_total = 0.0
        count = 0

        for i in range(1, len(recent)):
            x1, y1, _ = recent[i - 1]
            x2, y2, _ = recent[i]
            dx_total += (x2 - x1)
            dy_total += (y2 - y1)
            count += 1

        if count == 0:
            return "unknown"

        avg_dx = dx_total / count
        avg_dy = dy_total / count

        # Calculate angle in degrees (0 = right, 90 = down, etc.)
        angle = math.degrees(math.atan2(avg_dy, avg_dx))

        return self._angle_to_direction(angle)

    def is_moving_toward_point(self, track: Track,
                                target: Tuple[int, int],
                                angle_threshold: float = 60.0) -> bool:
        """
        Check if a track is moving toward a specific point (e.g., zone center).
        """
        recent = track.get_recent_trajectory(self.min_points)
        if len(recent) < 2:
            return False

        cx, cy = track.centroid
        tx, ty = target

        # Vector from current position to target
        target_angle = math.degrees(math.atan2(ty - cy, tx - cx))

        # Movement vector
        x1, y1, _ = recent[-2]
        x2, y2, _ = recent[-1]
        move_angle = math.degrees(math.atan2(y2 - y1, x2 - x1))

        # Angular difference
        diff = abs(target_angle - move_angle) % 360
        if diff > 180:
            diff = 360 - diff

        return diff < angle_threshold

    def is_moving_toward_zone(self, track: Track,
                               zone_center: Tuple[int, int]) -> bool:
        """Check if track is moving toward a zone center."""
        return self.is_moving_toward_point(track, zone_center)

    def get_direction_label(self, track: Track) -> str:
        """Get human-readable direction label."""
        direction = self.analyze_direction(track)
        if direction in self.DIRECTIONS:
            return self.DIRECTIONS[direction][1]
        return "Unknown"

    def get_movement_angle(self, track: Track) -> Optional[float]:
        """Get precise movement angle in degrees."""
        recent = track.get_recent_trajectory(self.min_points)
        if len(recent) < 2:
            return None

        dx = recent[-1][0] - recent[0][0]
        dy = recent[-1][1] - recent[0][1]

        if abs(dx) < 1 and abs(dy) < 1:
            return None

        return math.degrees(math.atan2(dy, dx))

    @staticmethod
    def _angle_to_direction(angle: float) -> str:
        """Convert angle to 8-direction classification."""
        # Normalize angle to [0, 360)
        angle = angle % 360

        if 337.5 <= angle or angle < 22.5:
            return "right"
        elif 22.5 <= angle < 67.5:
            return "down_right"
        elif 67.5 <= angle < 112.5:
            return "down"
        elif 112.5 <= angle < 157.5:
            return "down_left"
        elif 157.5 <= angle < 202.5:
            return "left"
        elif 202.5 <= angle < 247.5:
            return "up_left"
        elif 247.5 <= angle < 292.5:
            return "up"
        elif 292.5 <= angle < 337.5:
            return "up_right"
        return "unknown"
