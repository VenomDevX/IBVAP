"""
IBVAP — Track Data Class
Represents a tracked object with trajectory history.
"""

import time
from dataclasses import dataclass, field


@dataclass
class Track:
    """A tracked object with full trajectory history."""

    track_id: int
    object_type: str  # "person", "car", etc.
    camera_id: str

    # Current state
    bbox: tuple[int, int, int, int] = (0, 0, 0, 0)
    confidence: float = 0.0
    is_active: bool = True

    # Trajectory history — list of (centroid_x, centroid_y, timestamp)
    trajectory: list[tuple[int, int, float]] = field(default_factory=list)

    # Timing
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)

    # Zone context (updated by spatial module)
    current_zones: list[str] = field(default_factory=list)
    zone_entry_times: dict = field(default_factory=dict)  # zone_id -> entry_time

    # Behavior flags (updated by behavior engine)
    is_loitering: bool = False
    has_crossed_fence: bool = False
    movement_direction: str = "unknown"

    # Features
    color: str = "Unknown"
    license_plate: str = "Unknown"

    # Risk Assessment
    risk_score: float = 0.0
    risk_level: str = "low"
    risk_factors: list[str] = field(default_factory=list)

    @property
    def centroid(self) -> tuple[int, int]:
        """Current centroid position."""
        if self.trajectory:
            return (self.trajectory[-1][0], self.trajectory[-1][1])
        x1, y1, x2, y2 = self.bbox
        return ((x1 + x2) // 2, (y1 + y2) // 2)

    @property
    def duration(self) -> float:
        """Duration this track has been alive (seconds)."""
        return self.last_seen - self.first_seen

    @property
    def trajectory_length(self) -> int:
        """Number of trajectory points recorded."""
        return len(self.trajectory)

    @property
    def total_distance(self) -> float:
        """Total distance traveled in pixels."""
        if len(self.trajectory) < 2:
            return 0.0
        total = 0.0
        for i in range(1, len(self.trajectory)):
            x1, y1, _ = self.trajectory[i - 1]
            x2, y2, _ = self.trajectory[i]
            total += ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
        return total

    @property
    def average_speed(self) -> float:
        """Average speed in pixels per second."""
        if self.duration <= 0:
            return 0.0
        return self.total_distance / self.duration

    def update(self, bbox: tuple[int, int, int, int], confidence: float, timestamp: float | None = None):
        """Update track with new detection."""
        self.bbox = bbox
        self.confidence = confidence
        self.last_seen = timestamp or time.time()
        self.is_active = True

        # Calculate centroid and add to trajectory
        x1, y1, x2, y2 = bbox
        cx = (x1 + x2) // 2
        cy = (y1 + y2) // 2
        self.trajectory.append((cx, cy, self.last_seen))

        # Keep trajectory manageable (last 500 points)
        if len(self.trajectory) > 500:
            self.trajectory = self.trajectory[-500:]

    def get_recent_trajectory(self, n: int = 30) -> list[tuple[int, int, float]]:
        """Get the last N trajectory points."""
        return self.trajectory[-n:]

    def get_velocity(self) -> tuple[float, float]:
        """Get current velocity vector (pixels/second)."""
        if len(self.trajectory) < 2:
            return (0.0, 0.0)
        x1, y1, t1 = self.trajectory[-2]
        x2, y2, t2 = self.trajectory[-1]
        dt = t2 - t1
        if dt <= 0:
            return (0.0, 0.0)
        return ((x2 - x1) / dt, (y2 - y1) / dt)

    def to_dict(self) -> dict:
        """JSON-serializable representation."""
        return {
            "track_id": self.track_id,
            "object_type": self.object_type,
            "camera_id": self.camera_id,
            "bbox": list(self.bbox),
            "centroid": list(self.centroid),
            "confidence": round(self.confidence, 3),
            "is_active": self.is_active,
            "duration": round(self.duration, 2),
            "trajectory_length": self.trajectory_length,
            "total_distance": round(self.total_distance, 1),
            "average_speed": round(self.average_speed, 1),
            "current_zones": self.current_zones,
            "is_loitering": self.is_loitering,
            "has_crossed_fence": self.has_crossed_fence,
            "movement_direction": self.movement_direction,
            "color": self.color,
            "license_plate": self.license_plate,
            "risk_score": round(self.risk_score, 1),
            "risk_level": self.risk_level,
            "risk_factors": self.risk_factors,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
        }
