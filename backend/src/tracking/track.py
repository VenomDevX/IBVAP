"""
IBVAP — Track Data Class
Represents a tracked object with trajectory history.
"""

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import numpy as np

# The custom 13-class coarse detector has a trained "night_vision_object"
# catch-all for IR/thermal blobs that the classifier head predicts directly
# at night instead of car/truck/motorcycle. These tunables let a later,
# clearer-frame detection upgrade a track away from that generic label
# without retraining the model — see thresholds.yaml `tracking:` section,
# applied once at startup via configure_type_upgrade().
NIGHT_VISION_CATCHALL = "night_vision_object"
VEHICLE_CLASSES = {"car", "truck", "bus", "motorcycle", "bicycle"}
TYPE_UPGRADE_CONFIDENCE = 0.45
TYPE_UPGRADE_MARGIN = 0.10


def configure_type_upgrade(confidence: float, margin: float) -> None:
    """Set the module-level upgrade thresholds from thresholds.yaml."""
    global TYPE_UPGRADE_CONFIDENCE, TYPE_UPGRADE_MARGIN
    TYPE_UPGRADE_CONFIDENCE = float(confidence)
    TYPE_UPGRADE_MARGIN = float(margin)


@dataclass
class Track:
    """A tracked object with full trajectory history."""

    track_id: int
    object_type: str  # "person", "car", etc.
    camera_id: str
    session_id: str = "legacy"
    track_uuid: str = ""

    # Current state
    bbox: tuple[int, int, int, int] = (0, 0, 0, 0)
    confidence: float = 0.0
    is_active: bool = True
    status: str = "NEW"  # NEW | ACTIVE | LOST | CLOSED

    # Trajectory history — list of (centroid_x, centroid_y, timestamp)
    trajectory: list[tuple[int, int, float]] = field(default_factory=list)

    # Timing
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)

    # Zone context (updated by spatial module)
    current_zones: list[str] = field(default_factory=list)
    zone_entry_times: dict = field(default_factory=dict)  # zone_id -> entry_time
    zone_session_ids: dict = field(default_factory=dict)  # zone_id -> collision-safe visit id

    # Behavior flags (updated by behavior engine)
    is_loitering: bool = False
    has_crossed_fence: bool = False
    movement_direction: str = "unknown"

    # Features
    color: str = "Unknown"
    license_plate: str = "Unknown"
    plate_confidence: float = 0.0

    # Identity (face recognition)
    identity_label: str = "unknown"
    identity_score: float = 0.0
    identity_status: str = "unknown"  # known | uncertain | unknown | wanted

    # Best number-plate view the detector found inside this vehicle (full-res crop).
    plate_crop: Any = field(default=None, repr=False, compare=False)
    plate_crop_score: float = 0.0

    # Watchlist hit (WatchlistHit.to_dict()) for this track's face or plate.
    watchlist: dict | None = None

    # Fine-grained type (stage 2 classifier, military crops only).
    # "unknown" means either not yet classified or below the confidence gate;
    # consumers should fall back to object_type, which is always populated.
    fine_type: str = "unknown"
    fine_confidence: float = 0.0

    # Risk Assessment
    risk_score: float = 0.0
    risk_level: str = "low"
    risk_factors: list[str] = field(default_factory=list)
    score_breakdown: dict = field(default_factory=dict)

    # Best-frame state. The image itself is stored by the evidence service; the
    # track only keeps the quality decision and path.
    best_frame_score: float = 0.0
    best_frame_timestamp: float | None = None
    best_snapshot_path: str | None = None
    best_frame: Any = field(default=None, repr=False, compare=False)
    best_face_quality: float = 0.0
    plate_observations: list[dict] = field(default_factory=list)

    # Object-type upgrade state (see NIGHT_VISION_CATCHALL above). raw_class
    # is the very first detector label this track ever got — an audit trail
    # that's never overwritten, even after object_type upgrades away from it.
    raw_class: str = ""
    suspected_type: str | None = None
    type_confidence: float = 0.0
    class_votes: dict[str, float] = field(default_factory=dict)

    def __post_init__(self):
        if not self.track_uuid:
            # UUID5 is stable for the same camera session/tracker tuple and
            # cannot collide when ByteTrack restarts its numeric counter.
            identity = f"{self.camera_id}:{self.session_id}:{self.track_id}"
            self.track_uuid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"ibvap:{identity}"))
        if not self.raw_class:
            self.raw_class = self.object_type
        if not self.type_confidence:
            self.type_confidence = self.confidence
        self.class_votes.setdefault(self.object_type, self.confidence)

    def effective_label(self) -> str:
        """Human-facing label — enriches the night-vision catch-all with a
        suspected sub-type when one has been recovered, without changing the
        machine-readable `object_type`/`event_type` used for filtering."""
        if self.object_type == NIGHT_VISION_CATCHALL and self.suspected_type:
            return f"{NIGHT_VISION_CATCHALL} (suspected {self.suspected_type})"
        return self.object_type

    def _maybe_upgrade_object_type(self, new_class: str, new_conf: float) -> None:
        """Called from update() with each new frame's detected class. A
        track's object_type is normally frozen at creation; this lets a
        later, more confident vehicle-class read supersede an initial
        night_vision_object guess (or a weaker vehicle-class guess)."""
        if new_class == self.object_type:
            if new_conf > self.type_confidence:
                self.type_confidence = new_conf
            return
        if new_class not in VEHICLE_CLASSES:
            return
        if self.object_type == NIGHT_VISION_CATCHALL:
            if new_conf >= TYPE_UPGRADE_CONFIDENCE:
                self.object_type = new_class
                self.suspected_type = new_class
                self.type_confidence = new_conf
            elif new_conf >= self.class_votes.get(new_class, 0.0):
                # Not confident enough to fully commit, but worth surfacing
                # as a hint via effective_label().
                self.suspected_type = new_class
        elif new_conf > self.type_confidence + TYPE_UPGRADE_MARGIN:
            self.object_type = new_class
            self.suspected_type = None
            self.type_confidence = new_conf

    @property
    def watchlist_status(self) -> str:
        """wanted | authorized | vip | none"""
        return self.watchlist["list_type"] if self.watchlist else "none"

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
        # Vectorised: read by upsert, average_speed and the direction/loitering
        # checks for every track each frame, over up to 500 points.
        points = np.asarray(self.trajectory, dtype=float)[:, :2]
        steps = np.diff(points, axis=0)
        return float(np.hypot(steps[:, 0], steps[:, 1]).sum())

    @property
    def average_speed(self) -> float:
        """Average speed in pixels per second."""
        if self.duration <= 0:
            return 0.0
        return self.total_distance / self.duration

    def update(
        self,
        bbox: tuple[int, int, int, int],
        confidence: float,
        timestamp: float | None = None,
        class_name: str | None = None,
    ):
        """Update track with new detection.

        class_name (this frame's detected class, if known) feeds the
        object_type upgrade vote — see _maybe_upgrade_object_type. It's
        optional because not every caller (e.g. the ByteTrack reconcile
        fallback for a class it can't re-derive) has it on hand.
        """
        self.bbox = bbox
        self.confidence = confidence
        self.last_seen = timestamp or time.time()
        self.is_active = True
        self.status = "ACTIVE"

        # Calculate centroid and add to trajectory
        x1, y1, x2, y2 = bbox
        cx = (x1 + x2) // 2
        cy = (y1 + y2) // 2
        self.trajectory.append((cx, cy, self.last_seen))

        # Keep trajectory manageable (last 500 points)
        if len(self.trajectory) > 500:
            self.trajectory = self.trajectory[-500:]

        if class_name:
            self.class_votes[class_name] = max(self.class_votes.get(class_name, 0.0), confidence)
            self._maybe_upgrade_object_type(class_name, confidence)

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
            "track_uuid": self.track_uuid,
            "session_id": self.session_id,
            "object_type": self.object_type,
            "raw_class": self.raw_class,
            "suspected_type": self.suspected_type,
            "effective_label": self.effective_label(),
            "camera_id": self.camera_id,
            "bbox": list(self.bbox),
            "centroid": list(self.centroid),
            "confidence": round(self.confidence, 3),
            "is_active": self.is_active,
            "status": self.status,
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
            "plate_confidence": round(self.plate_confidence, 3),
            "identity_label": self.identity_label,
            "identity_score": round(self.identity_score, 3),
            "identity_status": self.identity_status,
            "watchlist": self.watchlist,
            "fine_type": self.fine_type,
            "fine_confidence": round(self.fine_confidence, 3),
            "risk_score": round(self.risk_score, 1),
            "risk_level": self.risk_level,
            "risk_factors": self.risk_factors,
            "score_breakdown": self.score_breakdown,
            "zone_entered_at": self.zone_entry_times,
            "zone_session_ids": self.zone_session_ids,
            "best_frame_score": round(self.best_frame_score, 3),
            "best_frame_timestamp": self.best_frame_timestamp,
            "best_snapshot_path": self.best_snapshot_path,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
        }
