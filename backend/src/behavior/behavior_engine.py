"""
IBVAP — Behavior Engine
Combines detection, tracking, spatial, and temporal signals to classify behaviors.
"""

import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum

from src.tracking.track import Track


class BehaviorType(Enum):
    """Classified behavior types."""

    NORMAL = "normal"
    RESTRICTED_ZONE_ENTRY = "restricted_zone_entry"
    FENCE_CROSSING = "fence_crossing"
    LOITERING = "loitering"
    WRONG_DIRECTION = "wrong_direction"
    NIGHT_MOVEMENT = "night_movement"
    APPROACHING_BOUNDARY = "approaching_boundary"
    SUSPICIOUS_VEHICLE = "suspicious_vehicle"
    COMBINED_SUSPICIOUS = "combined_suspicious"


@dataclass
class BehaviorEvent:
    """A classified behavior event for a track."""

    event_id: str
    track_id: int
    camera_id: str
    behavior_type: BehaviorType
    timestamp: float
    confidence: float = 1.0
    details: dict = field(default_factory=dict)
    contributing_factors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "track_id": self.track_id,
            "camera_id": self.camera_id,
            "behavior_type": self.behavior_type.value,
            "timestamp": self.timestamp,
            "confidence": self.confidence,
            "details": self.details,
            "contributing_factors": self.contributing_factors,
        }


class BehaviorEngine:
    """
    Rule-based behavior classification engine.
    Combines all analysis signals to detect meaningful behaviors.
    """

    def __init__(self):
        self._event_counter: int = 0
        self._recent_events = deque(maxlen=2000)
        # Cooldown: (track_id, behavior_type) -> last_event_time
        self._cooldowns: dict[tuple, float] = {}
        self._cooldown_seconds: float = 30.0

    def analyze_track(
        self,
        track: Track,
        zone_context: dict,
        temporal_context: dict,
        direction_context: dict,
        fence_context: dict,
        apply_cooldown: bool = True,
    ) -> list[BehaviorEvent]:
        """
        Analyze a track's behavior using all available context.

        Args:
            track: The tracked object
            zone_context: {in_restricted: bool, in_buffer: bool, zones: [...]}
            temporal_context: {is_night: bool, is_loitering: bool, duration: float}
            direction_context: {direction: str, toward_restricted: bool}
            fence_context: {crossed: bool, approaching: bool, distance: float}

        Returns:
            List of behavior events detected
        """
        events = []
        self._apply_cooldown = apply_cooldown

        # --- Check: Restricted Zone Entry ---
        if zone_context.get("in_restricted", False):
            event = self._create_event(
                track,
                BehaviorType.RESTRICTED_ZONE_ENTRY,
                details={
                    "zones": zone_context.get("zones", []),
                    "object_type": track.object_type,
                },
                factors=["Object in restricted zone"],
            )
            if event:
                events.append(event)

        # --- Check: Fence Crossing ---
        if fence_context.get("crossed", False):
            event = self._create_event(
                track,
                BehaviorType.FENCE_CROSSING,
                details={
                    "fence_id": fence_context.get("fence_id", ""),
                    "direction": fence_context.get("crossing_direction", ""),
                },
                factors=["Virtual fence crossed"],
            )
            if event:
                events.append(event)

        # --- Check: Loitering ---
        if temporal_context.get("is_loitering", False):
            duration = temporal_context.get("loiter_duration", 0)
            event = self._create_event(
                track,
                BehaviorType.LOITERING,
                details={
                    "duration_seconds": round(duration, 1),
                    "zone": temporal_context.get("loiter_zone", ""),
                },
                factors=[f"Loitering for {duration:.0f} seconds"],
            )
            if event:
                events.append(event)

        # --- Check: Night Movement ---
        if temporal_context.get("is_night", False) and track.is_active and track.average_speed > 0:
            event = self._create_event(
                track,
                BehaviorType.NIGHT_MOVEMENT,
                details={
                    "brightness": temporal_context.get("brightness", 0),
                    "is_night_time": temporal_context.get("is_night_time", False),
                },
                factors=["Movement during night-time conditions"],
            )
            if event:
                events.append(event)

        # --- Check: Approaching Boundary ---
        if fence_context.get("approaching", False):
            event = self._create_event(
                track,
                BehaviorType.APPROACHING_BOUNDARY,
                details={
                    "distance": fence_context.get("distance", 0),
                    "fence_name": fence_context.get("fence_name", ""),
                },
                factors=[f"Approaching boundary ({fence_context.get('distance', 0):.0f}px)"],
            )
            if event:
                events.append(event)

        # --- Check: Wrong/Unexpected Direction ---
        if direction_context.get("toward_restricted", False):
            event = self._create_event(
                track,
                BehaviorType.WRONG_DIRECTION,
                details={
                    "direction": direction_context.get("direction", ""),
                    "moving_toward": "restricted zone",
                },
                factors=["Moving toward restricted zone"],
            )
            if event:
                events.append(event)

        # --- Check: Combined Suspicious (3+ individual flags) ---
        if len(events) >= 3:
            combined_factors = []
            for e in events:
                combined_factors.extend(e.contributing_factors)

            combined = self._create_event(
                track,
                BehaviorType.COMBINED_SUSPICIOUS,
                details={"individual_events": len(events)},
                factors=combined_factors,
                force=True,
            )
            if combined:
                events.append(combined)

        self._recent_events.extend(events)
        return events

    def _create_event(
        self,
        track: Track,
        behavior_type: BehaviorType,
        details: dict = None,
        factors: list[str] = None,
        force: bool = False,
    ) -> BehaviorEvent | None:
        """Create a behavior event with cooldown check."""
        now = time.time()
        key = (track.track_id, behavior_type.value)

        if not getattr(self, "_apply_cooldown", True):
            return BehaviorEvent(
                event_id="", track_id=track.track_id, camera_id=track.camera_id,
                behavior_type=behavior_type, timestamp=now,
                details=details or {}, contributing_factors=factors or [],
            )

        if len(self._cooldowns) > 512:
            ccut = now - self._cooldown_seconds * 4
            self._cooldowns = {k: t for k, t in self._cooldowns.items() if t > ccut}

        # Cooldown check
        if not force and key in self._cooldowns:
            if now - self._cooldowns[key] < self._cooldown_seconds:
                return None

        self._event_counter += 1
        self._cooldowns[key] = now

        return BehaviorEvent(
            event_id=f"BEV_{self._event_counter:06d}",
            track_id=track.track_id,
            camera_id=track.camera_id,
            behavior_type=behavior_type,
            timestamp=now,
            details=details or {},
            contributing_factors=factors or [],
        )

    def get_recent_events(self, limit: int = 100) -> list[dict]:
        return [e.to_dict() for e in list(self._recent_events)[-limit:]]

    def get_statistics(self) -> dict:
        from collections import Counter

        type_counts = Counter(e.behavior_type.value for e in self._recent_events)
        return {
            "total_events": len(self._recent_events),
            "event_types": dict(type_counts),
        }
