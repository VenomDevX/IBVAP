"""
IBVAP — Virtual Fence Detector
Detects line/boundary crossing events using trajectory analysis.
"""

from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
import time
import math

import numpy as np
import cv2
from loguru import logger

from src.tracking.track import Track


@dataclass
class FenceLine:
    """A virtual fence line definition."""
    fence_id: str
    name: str
    camera_id: str
    point_a: Tuple[int, int]
    point_b: Tuple[int, int]
    trigger_direction: str = "both"  # "both", "top_to_bottom", "bottom_to_top"
    enabled: bool = True
    color: Tuple[int, int, int] = (0, 0, 255)


@dataclass
class FenceCrossingEvent:
    """Record of a fence crossing."""
    fence_id: str
    track_id: int
    camera_id: str
    crossing_time: float
    direction: str  # "top_to_bottom" or "bottom_to_top"
    object_type: str
    crossing_point: Tuple[int, int]


class FenceDetector:
    """
    Detects virtual fence line crossings using consecutive trajectory points.
    Uses line segment intersection to determine if and where crossing occurred.
    """

    def __init__(self):
        self._fences: Dict[str, FenceLine] = {}
        self._crossing_history: Dict[str, set] = {}  # fence_id -> set of track_ids that crossed
        from collections import deque
        self._recent_crossings = deque(maxlen=500)

    def load_from_config(self, config: dict):
        """Load fences from YAML config."""
        fences_config = config.get("fences", {})

        for camera_id, camera_fences in fences_config.items():
            for fence_cfg in camera_fences:
                fence = FenceLine(
                    fence_id=fence_cfg["id"],
                    name=fence_cfg["name"],
                    camera_id=camera_id,
                    point_a=tuple(fence_cfg["point_a"]),
                    point_b=tuple(fence_cfg["point_b"]),
                    trigger_direction=fence_cfg.get("trigger_direction", "both"),
                    enabled=fence_cfg.get("enabled", True),
                    color=tuple(fence_cfg.get("color", [0, 0, 255])),
                )
                self.add_fence(fence)
                logger.info(f"Loaded fence: {fence.name} for {camera_id}")

    def add_fence(self, fence: FenceLine):
        """Add a virtual fence."""
        self._fences[fence.fence_id] = fence
        self._crossing_history[fence.fence_id] = set()

    def check_crossing(self, track: Track) -> List[FenceCrossingEvent]:
        """
        Check if a track has crossed any fence.
        Uses the last two trajectory points to detect line crossing.
        """
        events = []

        if len(track.trajectory) < 2:
            return events

        # Get last two positions
        prev_x, prev_y, _ = track.trajectory[-2]
        curr_x, curr_y, curr_t = track.trajectory[-1]

        for fence_id, fence in self._fences.items():
            if not fence.enabled or fence.camera_id != track.camera_id:
                continue

            # Skip if already crossed this fence
            if track.track_id in self._crossing_history.get(fence_id, set()):
                continue

            # Check line segment intersection
            crossed, cross_point = self._line_intersection(
                (prev_x, prev_y), (curr_x, curr_y),
                fence.point_a, fence.point_b
            )

            if crossed:
                # Determine crossing direction
                direction = self._get_crossing_direction(
                    (prev_x, prev_y), (curr_x, curr_y),
                    fence.point_a, fence.point_b
                )

                # Check if direction matches trigger condition
                if fence.trigger_direction != "both" and direction != fence.trigger_direction:
                    continue

                event = FenceCrossingEvent(
                    fence_id=fence_id,
                    track_id=track.track_id,
                    camera_id=track.camera_id,
                    crossing_time=curr_t,
                    direction=direction,
                    object_type=track.object_type,
                    crossing_point=cross_point,
                )

                events.append(event)
                self._crossing_history[fence_id].add(track.track_id)
                self._recent_crossings.append(event)
                track.has_crossed_fence = True

                logger.info(
                    f"Fence crossing: Track {track.track_id} crossed "
                    f"{fence.name} ({direction})"
                )

        return events

    def check_approaching(self, track: Track, threshold_pixels: float = 50.0) -> List[dict]:
        """Check if a track is approaching any fence line."""
        approaching = []

        if not track.trajectory:
            return approaching

        cx, cy = track.centroid

        for fence_id, fence in self._fences.items():
            if not fence.enabled or fence.camera_id != track.camera_id:
                continue

            dist = self._point_to_line_distance(
                (cx, cy), fence.point_a, fence.point_b
            )

            if dist < threshold_pixels:
                approaching.append({
                    "fence_id": fence_id,
                    "fence_name": fence.name,
                    "distance": round(dist, 1),
                    "track_id": track.track_id,
                })

        return approaching

    @staticmethod
    def _line_intersection(
        p1: Tuple[int, int], p2: Tuple[int, int],
        p3: Tuple[int, int], p4: Tuple[int, int]
    ) -> Tuple[bool, Optional[Tuple[int, int]]]:
        """
        Check if line segments (p1-p2) and (p3-p4) intersect.
        Returns (intersects, intersection_point).
        """
        x1, y1 = p1
        x2, y2 = p2
        x3, y3 = p3
        x4, y4 = p4

        denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
        if abs(denom) < 1e-10:
            return False, None

        t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denom
        u = -((x1 - x2) * (y1 - y3) - (y1 - y2) * (x1 - x3)) / denom

        if 0 <= t <= 1 and 0 <= u <= 1:
            ix = int(x1 + t * (x2 - x1))
            iy = int(y1 + t * (y2 - y1))
            return True, (ix, iy)

        return False, None

    @staticmethod
    def _get_crossing_direction(
        prev: Tuple[int, int], curr: Tuple[int, int],
        line_a: Tuple[int, int], line_b: Tuple[int, int]
    ) -> str:
        """Determine crossing direction relative to the fence line."""
        # Use cross product to determine which side the points are on
        dx = line_b[0] - line_a[0]
        dy = line_b[1] - line_a[1]

        cross_prev = dx * (prev[1] - line_a[1]) - dy * (prev[0] - line_a[0])
        cross_curr = dx * (curr[1] - line_a[1]) - dy * (curr[0] - line_a[0])

        if cross_prev > 0 and cross_curr <= 0:
            return "top_to_bottom"
        elif cross_prev <= 0 and cross_curr > 0:
            return "bottom_to_top"
        return "unknown"

    @staticmethod
    def _point_to_line_distance(
        point: Tuple[int, int],
        line_a: Tuple[int, int],
        line_b: Tuple[int, int]
    ) -> float:
        """Calculate minimum distance from a point to a line segment."""
        px, py = point
        ax, ay = line_a
        bx, by = line_b

        dx = bx - ax
        dy = by - ay
        seg_len_sq = dx * dx + dy * dy

        if seg_len_sq < 1e-10:
            return math.sqrt((px - ax) ** 2 + (py - ay) ** 2)

        t = max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / seg_len_sq))
        proj_x = ax + t * dx
        proj_y = ay + t * dy

        return math.sqrt((px - proj_x) ** 2 + (py - proj_y) ** 2)

    def get_recent_crossings(self, limit: int = 50) -> List[dict]:
        return [
            {
                "fence_id": e.fence_id,
                "track_id": e.track_id,
                "camera_id": e.camera_id,
                "crossing_time": e.crossing_time,
                "direction": e.direction,
                "object_type": e.object_type,
            }
            for e in list(self._recent_crossings)[-limit:]
        ]

    @staticmethod
    def draw_fences(frame: np.ndarray, fences: List[FenceLine]) -> np.ndarray:
        """Draw fence lines on frame."""
        annotated = frame.copy()
        for fence in fences:
            if not fence.enabled:
                continue
            cv2.line(annotated, fence.point_a, fence.point_b, fence.color, 3)
            mid_x = (fence.point_a[0] + fence.point_b[0]) // 2
            mid_y = (fence.point_a[1] + fence.point_b[1]) // 2
            cv2.putText(
                annotated, fence.name, (mid_x - 30, mid_y - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, fence.color, 2
            )
        return annotated
