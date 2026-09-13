"""
IBVAP — Context Fusion Engine
Fuses multiple observations into coherent security events.
This is the CORE NOVELTY of IBVAP.
"""

import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field

from loguru import logger

from src.behavior.behavior_engine import BehaviorEvent, BehaviorType


@dataclass
class FusedEvent:
    """
    A fused security event combining multiple low-level observations.
    Instead of 5 separate alerts, we produce 1 coherent event.
    """

    event_id: str
    camera_id: str
    track_id: int
    timestamp: float
    object_type: str

    # Fused context
    event_type: str  # Primary event classification
    track_uuid: str = ""
    risk_score: float = 0.0
    risk_level: str = "low"

    # Contributing factors (for explainability)
    contributing_factors: list[str] = field(default_factory=list)
    behavior_events: list[str] = field(default_factory=list)  # behavior event IDs

    # Context signals
    spatial_context: dict = field(default_factory=dict)
    temporal_context: dict = field(default_factory=dict)
    identity_context: dict = field(default_factory=dict)
    vehicle_context: dict = field(default_factory=dict)

    # Evidence
    duration: float = 0.0
    evidence_path: str | None = None
    evidence_hash: str | None = None
    snapshot_path: str | None = None
    zone_id: str | None = None
    state: str = "PENDING"
    opened_at: float | None = None
    last_updated: float | None = None
    closed_at: float | None = None
    dedupe_key: str = ""
    score_breakdown: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "camera_id": self.camera_id,
            "track_id": self.track_id,
            "track_uuid": self.track_uuid,
            "timestamp": self.timestamp,
            "object_type": self.object_type,
            "event_type": self.event_type,
            "risk_score": round(self.risk_score, 1),
            "risk_level": self.risk_level,
            "contributing_factors": self.contributing_factors,
            "spatial_context": self.spatial_context,
            "temporal_context": self.temporal_context,
            "identity_context": self.identity_context,
            "vehicle_context": self.vehicle_context,
            "evidence_path": self.evidence_path,
            "evidence_hash": self.evidence_hash,
            "duration": round(self.duration, 1),
            "zone_id": self.zone_id,
            "state": self.state,
            "opened_at": self.opened_at,
            "last_updated": self.last_updated,
            "closed_at": self.closed_at,
            "dedupe_key": self.dedupe_key,
            "score_breakdown": self.score_breakdown,
        }


class ContextFusion:
    """
    Fuses low-level behavior events and contextual signals into
    coherent, explainable security events.

    KEY PRINCIPLE: One fused event instead of multiple redundant alerts.

    Example:
        Instead of:
            Alert 1: Person detected
            Alert 2: Night detected
            Alert 3: Person in zone
            Alert 4: Person moving
            Alert 5: Loitering

        We produce:
            CRITICAL EVENT: Unknown person in restricted zone during night-time.
            Contributing: zone entry, loitering (48s), movement toward boundary, unknown identity.
    """

    def __init__(
        self,
        fusion_cooldown: float = 120.0,
        incident_cooldown: float = 60.0,
        max_events_per_minute: int = 20,
    ):
        self._event_counter: int = 0
        self._fused_events = deque(maxlen=5000)
        # Track-level deduplication handles stable trackers. Incident-level
        # deduplication also handles tracker churn, where the same person is
        # repeatedly assigned a new track id and previously flooded the DB.
        self._last_fusion: dict[tuple, tuple[float, tuple]] = {}
        self._last_incident: dict[tuple, tuple[float, int]] = {}
        self._record_times: dict[str, deque[float]] = defaultdict(deque)
        self._last_budget_warning: dict[str, float] = {}
        self._fusion_cooldown = max(1.0, float(fusion_cooldown))
        self._incident_cooldown = max(1.0, float(incident_cooldown))
        self._max_events_per_minute = max(0, int(max_events_per_minute))

    def fuse_events(
        self,
        track_id: int,
        camera_id: str,
        object_type: str,
        behavior_events: list[BehaviorEvent],
        spatial_context: dict,
        temporal_context: dict,
        track_uuid: str = "",
        identity_context: dict | None = None,
        vehicle_context: dict | None = None,
        track_duration: float = 0.0,
    ) -> FusedEvent | None:
        """
        Fuse multiple behavior events and context signals for a single track.

        Returns a FusedEvent if the combined signals are significant enough,
        or None if they don't warrant a fused event.
        """
        now = time.time()

        if not behavior_events:
            return None

        # Collect all contributing factors
        all_factors = []
        behavior_types = set()
        behavior_ids = []

        for event in behavior_events:
            all_factors.extend(event.contributing_factors)
            behavior_types.add(event.behavior_type)
            behavior_ids.append(event.event_id)

        # Determine primary event type
        event_type = self._classify_fused_event(behavior_types, spatial_context, temporal_context)

        # Build additional context factors
        if temporal_context.get("is_night", False):
            all_factors.append("Night-time conditions")

        if identity_context and identity_context.get("identity") == "unknown":
            all_factors.append("Unknown identity")

        plate = vehicle_context.get("plate") if vehicle_context else None
        if plate and plate != "unknown":
            all_factors.append(f"Vehicle Plate: {plate}")
        elif vehicle_context and vehicle_context.get("plate") == "unknown":
            all_factors.append("Unknown vehicle plate")

        color = identity_context.get("color") if identity_context else None
        if color:
            all_factors.append(f"Dominant color: {color}")

        if track_duration > 30:
            all_factors.append(f"Prolonged presence ({track_duration:.0f}s)")

        # Semantic Description (Task 3)
        desc = f"A {color + ' ' if color else ''}{object_type}"
        if plate and plate != "unknown":
            desc += f" (Plate: {plate})"
        desc += " was detected"

        if spatial_context.get("in_restricted"):
            desc += " in restricted zone"
        elif spatial_context.get("fence_crossed"):
            desc += " crossing a fence"
        elif temporal_context.get("is_loitering"):
            desc += " loitering"
        temporal_context["semantic_description"] = desc

        # Deduplicate factors
        all_factors = list(dict.fromkeys(all_factors))

        # Only create fused event if there are meaningful signals
        if len(all_factors) < 1:
            return None

        self._event_counter += 1
        fused = FusedEvent(
            event_id=f"EVT_{uuid.uuid4().hex}",
            camera_id=camera_id,
            track_id=track_id,
            track_uuid=track_uuid,
            timestamp=now,
            object_type=object_type,
            event_type=event_type,
            contributing_factors=all_factors,
            behavior_events=behavior_ids,
            spatial_context=spatial_context,
            temporal_context=temporal_context,
            identity_context=identity_context or {},
            vehicle_context=vehicle_context or {},
            duration=track_duration,
            zone_id=(temporal_context.get("loiter_zone") or next(iter(spatial_context.get("zones", [])), None)),
        )

        return fused

    @staticmethod
    def _signature(event: FusedEvent) -> tuple:
        return (
            event.event_type,
            event.risk_level,
            event.spatial_context.get("fence_crossed", False),
            tuple(sorted(event.spatial_context.get("zones", []))),
        )

    @staticmethod
    def _incident_key(event: FusedEvent) -> tuple:
        """A stable incident identity that survives tracker-id churn."""
        return (
            event.camera_id,
            event.event_type,
            event.object_type,
            tuple(sorted(event.spatial_context.get("zones", []))),
            bool(event.spatial_context.get("fence_crossed", False)),
        )

    @staticmethod
    def _level(level: str) -> int:
        return {"low": 0, "medium": 1, "high": 2, "critical": 3}.get(level, 0)

    def should_record(self, event: FusedEvent) -> bool:
        """Bound persistence while preserving state changes and escalations."""
        now = time.time()
        cutoff = now - max(self._fusion_cooldown, self._incident_cooldown) * 4
        self._last_fusion = {k: v for k, v in self._last_fusion.items() if v[0] > cutoff}
        self._last_incident = {k: v for k, v in self._last_incident.items() if v[0] > cutoff}

        previous = self._last_fusion.get((event.camera_id, event.track_id))
        track_changed = previous is None or previous[1] != self._signature(event)
        track_due = previous is None or now - previous[0] >= self._fusion_cooldown
        if not track_changed and not track_due:
            return False

        incident = self._last_incident.get(self._incident_key(event))
        if incident is not None:
            escalating = self._level(event.risk_level) > incident[1]
            if not escalating and now - incident[0] < self._incident_cooldown:
                return False

        times = self._record_times[event.camera_id]
        while times and now - times[0] >= 60:
            times.popleft()
        if len(times) >= self._max_events_per_minute:
            last_warning = self._last_budget_warning.get(event.camera_id, 0.0)
            if now - last_warning >= 60:
                logger.warning(
                    "Event persistence budget reached for camera {} ({} per minute)",
                    event.camera_id,
                    self._max_events_per_minute,
                )
                self._last_budget_warning[event.camera_id] = now
            return False
        return True

    def mark_recorded(self, event: FusedEvent) -> None:
        now = time.time()
        self._last_fusion[(event.camera_id, event.track_id)] = (now, self._signature(event))
        self._last_incident[self._incident_key(event)] = (now, self._level(event.risk_level))
        self._record_times[event.camera_id].append(now)
        self._fused_events.append(event)
        logger.info(
            "Recorded event {} camera={} track={} risk={}",
            event.event_type,
            event.camera_id,
            event.track_id,
            event.risk_level,
        )

    def _classify_fused_event(
        self,
        behavior_types: set,
        spatial_context: dict,
        temporal_context: dict,
    ) -> str:
        """
        Determine the primary event classification based on combined signals.
        Uses a priority hierarchy.
        """
        is_night = temporal_context.get("is_night", False)
        in_restricted = spatial_context.get("in_restricted", False)

        # Combined suspicious — highest priority
        if BehaviorType.COMBINED_SUSPICIOUS in behavior_types:
            if in_restricted and is_night:
                return "critical_intrusion"
            return "combined_suspicious_activity"

        # Fence crossing
        if BehaviorType.FENCE_CROSSING in behavior_types:
            if is_night:
                return "night_fence_crossing"
            return "fence_crossing"

        # Restricted zone entry
        if BehaviorType.RESTRICTED_ZONE_ENTRY in behavior_types:
            if BehaviorType.LOITERING in behavior_types:
                return "restricted_zone_loitering"
            if is_night:
                return "night_restricted_zone_entry"
            return "restricted_zone_entry"

        # Loitering
        if BehaviorType.LOITERING in behavior_types:
            if is_night:
                return "night_loitering"
            return "loitering"

        # Night movement
        if BehaviorType.NIGHT_MOVEMENT in behavior_types:
            return "night_movement"

        # Approaching boundary
        if BehaviorType.APPROACHING_BOUNDARY in behavior_types:
            return "boundary_approach"

        # Wrong direction
        if BehaviorType.WRONG_DIRECTION in behavior_types:
            return "unexpected_direction"

        return "general_activity"

    def get_recent_events(self, limit: int = 100) -> list[dict]:
        return [e.to_dict() for e in list(self._fused_events)[-limit:]]

    def get_events_by_camera(self, camera_id: str, limit: int = 50) -> list[dict]:
        return [e.to_dict() for e in self._fused_events if e.camera_id == camera_id][-limit:]

    def get_event(self, event_id: str) -> dict | None:
        for e in self._fused_events:
            if e.event_id == event_id:
                return e.to_dict()
        return None

    def get_statistics(self) -> dict:
        from collections import Counter

        type_counts = Counter(e.event_type for e in self._fused_events)
        level_counts = Counter(e.risk_level for e in self._fused_events)
        return {
            "total_fused_events": len(self._fused_events),
            "event_types": dict(type_counts),
            "risk_levels": dict(level_counts),
        }
