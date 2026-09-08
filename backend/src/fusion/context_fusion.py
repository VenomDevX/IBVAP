"""
IBVAP — Context Fusion Engine
Fuses multiple observations into coherent security events.
This is the CORE NOVELTY of IBVAP.
"""

import time
from typing import Dict, List, Optional
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
    risk_score: float = 0.0
    risk_level: str = "low"

    # Contributing factors (for explainability)
    contributing_factors: List[str] = field(default_factory=list)
    behavior_events: List[str] = field(default_factory=list)  # behavior event IDs

    # Context signals
    spatial_context: dict = field(default_factory=dict)
    temporal_context: dict = field(default_factory=dict)
    identity_context: dict = field(default_factory=dict)
    vehicle_context: dict = field(default_factory=dict)

    # Evidence
    duration: float = 0.0
    evidence_path: Optional[str] = None
    evidence_hash: Optional[str] = None
    snapshot_path: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "camera_id": self.camera_id,
            "track_id": self.track_id,
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
            "duration": round(self.duration, 1),
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

    def __init__(self):
        self._event_counter: int = 0
        self._fused_events: List[FusedEvent] = []
        # Deduplication: track_id -> last fused event time
        self._last_fusion: Dict[int, float] = {}
        self._fusion_cooldown: float = 30.0  # seconds

    def fuse_events(
        self,
        track_id: int,
        camera_id: str,
        object_type: str,
        behavior_events: List[BehaviorEvent],
        spatial_context: dict,
        temporal_context: dict,
        identity_context: Optional[dict] = None,
        vehicle_context: Optional[dict] = None,
        track_duration: float = 0.0,
    ) -> Optional[FusedEvent]:
        """
        Fuse multiple behavior events and context signals for a single track.

        Returns a FusedEvent if the combined signals are significant enough,
        or None if they don't warrant a fused event.
        """
        now = time.time()

        # Check cooldown
        if track_id in self._last_fusion:
            if now - self._last_fusion[track_id] < self._fusion_cooldown:
                return None

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
            desc += f" in restricted zone"
        elif spatial_context.get("fence_crossed"):
            desc += f" crossing a fence"
        elif temporal_context.get("is_loitering"):
            desc += f" loitering"
        temporal_context["semantic_description"] = desc

        # Deduplicate factors
        all_factors = list(dict.fromkeys(all_factors))

        # Only create fused event if there are meaningful signals
        if len(all_factors) < 1:
            return None

        self._event_counter += 1
        fused = FusedEvent(
            event_id=f"EVT_{int(now)}_{self._event_counter:04d}",
            camera_id=camera_id,
            track_id=track_id,
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
        )

        self._fused_events.append(fused)
        self._last_fusion[track_id] = now

        logger.info(
            f"Fused event: {event_type} | Track {track_id} | "
            f"Factors: {len(all_factors)} | Camera: {camera_id}"
        )

        return fused

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

    def get_recent_events(self, limit: int = 100) -> List[dict]:
        return [e.to_dict() for e in self._fused_events[-limit:]]

    def get_events_by_camera(self, camera_id: str, limit: int = 50) -> List[dict]:
        return [
            e.to_dict() for e in self._fused_events
            if e.camera_id == camera_id
        ][-limit:]

    def get_event(self, event_id: str) -> Optional[dict]:
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
