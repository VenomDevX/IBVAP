"""Track-aware incident lifecycle for fused observations.

Detections and behavior observations are deliberately transient. This module
turns them into one durable incident per track/rule/zone session.
"""

import time
import uuid
from collections import deque
from dataclasses import dataclass

from src.fusion.context_fusion import FusedEvent


@dataclass
class IncidentTransition:
    action: str  # opened | updated | escalated | closed
    event: FusedEvent


@dataclass
class _Incident:
    event: FusedEvent
    observations: deque[bool]
    last_seen: float
    last_persisted: float = 0.0
    absent_since: float | None = None
    highest_level: int = 0


class EventStateMachine:
    """Maintain PENDING/OPEN/ACTIVE/CLOSED incident state.

    The key contains the persistent track UUID, camera, rule, and current zone
    session. A tracker ID reused in another stream session therefore cannot
    update an older incident.
    """

    LEVELS = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}

    def __init__(
        self,
        confirmation_frames: int = 3,
        confirmation_window: int = 5,
        exit_grace_seconds: float = 2.0,
        cooldown_seconds: float = 30.0,
        update_interval_seconds: float = 1.0,
    ):
        self.confirmation_frames = max(1, int(confirmation_frames))
        self.confirmation_window = max(self.confirmation_frames, int(confirmation_window))
        self.exit_grace_seconds = max(0.0, float(exit_grace_seconds))
        self.cooldown_seconds = max(0.0, float(cooldown_seconds))
        self.update_interval_seconds = max(0.0, float(update_interval_seconds))
        self._incidents: dict[tuple, _Incident] = {}
        # track_uuid -> that track's incident keys. observe() runs once per
        # track per frame; scanning every incident each call was
        # O(tracks x incidents) on busy cameras.
        self._track_keys: dict[str, set[tuple]] = {}
        self._last_prune = 0.0

    @staticmethod
    def _key(event: FusedEvent) -> tuple:
        zone_session = event.temporal_context.get("zone_session_id") or event.zone_id or ""
        return (event.track_uuid, event.camera_id, event.event_type, zone_session)

    def _add(self, key: tuple, incident: _Incident) -> None:
        self._incidents[key] = incident
        self._track_keys.setdefault(key[0], set()).add(key)

    def _remove(self, key: tuple) -> None:
        self._incidents.pop(key, None)
        keys = self._track_keys.get(key[0])
        if keys is not None:
            keys.discard(key)
            if not keys:
                del self._track_keys[key[0]]

    def observe(
        self,
        track_uuid: str,
        candidates: list[FusedEvent],
        timestamp: float | None = None,
    ) -> list[IncidentTransition]:
        now = time.time() if timestamp is None else timestamp
        transitions: list[IncidentTransition] = []
        seen: set[tuple] = set()

        for candidate in candidates:
            candidate.track_uuid = candidate.track_uuid or track_uuid
            key = self._key(candidate)
            seen.add(key)
            incident = self._incidents.get(key)
            if incident and incident.event.state == "CLOSED":
                if now - (incident.event.closed_at or now) < self.cooldown_seconds:
                    continue
                self._remove(key)
                incident = None

            if incident is None:
                candidate.event_id = f"EVT_{uuid.uuid4().hex}"
                candidate.state = "PENDING"
                candidate.dedupe_key = ":".join(str(part) for part in key)
                incident = _Incident(
                    event=candidate,
                    observations=deque(maxlen=self.confirmation_window),
                    last_seen=now,
                    highest_level=self.LEVELS.get(candidate.risk_level, 0),
                )
                self._add(key, incident)

            incident.observations.append(True)
            incident.last_seen = now
            incident.absent_since = None
            stable_id = incident.event.event_id
            stable_state = incident.event.state
            opened_at = incident.event.opened_at
            incident.event = candidate
            incident.event.event_id = stable_id
            incident.event.state = stable_state
            incident.event.opened_at = opened_at
            incident.event.last_updated = now
            incident.event.dedupe_key = ":".join(str(part) for part in key)

            level = self.LEVELS.get(candidate.risk_level, 0)
            if stable_state == "PENDING":
                if sum(incident.observations) >= self.confirmation_frames:
                    incident.event.state = "OPEN"
                    incident.event.opened_at = now
                    incident.last_persisted = now
                    incident.highest_level = level
                    transitions.append(IncidentTransition("opened", incident.event))
            else:
                incident.event.state = "ACTIVE"
                incident.event.duration = max(
                    candidate.duration,
                    now - (incident.event.opened_at or now),
                )
                if level > incident.highest_level:
                    incident.highest_level = level
                    incident.last_persisted = now
                    transitions.append(IncidentTransition("escalated", incident.event))
                elif now - incident.last_persisted >= self.update_interval_seconds:
                    incident.last_persisted = now
                    transitions.append(IncidentTransition("updated", incident.event))

        # A missing condition advances its exit-grace timer. Pending candidates
        # receive false samples so N-of-M confirmation is genuinely temporal.
        for key in list(self._track_keys.get(track_uuid, ())):
            incident = self._incidents[key]
            if key in seen or incident.event.state == "CLOSED":
                continue
            incident.observations.append(False)
            if incident.event.state == "PENDING":
                if not any(incident.observations):
                    self._remove(key)
                continue
            if incident.absent_since is None:
                incident.absent_since = now
            if now - incident.absent_since >= self.exit_grace_seconds:
                incident.event.state = "CLOSED"
                incident.event.closed_at = now
                incident.event.last_updated = now
                incident.event.duration = max(
                    incident.event.duration,
                    now - (incident.event.opened_at or now),
                )
                transitions.append(IncidentTransition("closed", incident.event))

        self._prune(now)
        return transitions

    def expire_inactive(self, active_track_uuids: set[str], timestamp: float | None = None) -> list[IncidentTransition]:
        now = time.time() if timestamp is None else timestamp
        transitions: list[IncidentTransition] = []
        tracked = [track_uuid for track_uuid in self._track_keys if track_uuid not in active_track_uuids]
        for track_uuid in tracked:
            transitions.extend(self.observe(track_uuid, [], now))
        return transitions

    def close_all(self, timestamp: float | None = None) -> list[IncidentTransition]:
        now = time.time() if timestamp is None else timestamp
        transitions: list[IncidentTransition] = []
        for incident in self._incidents.values():
            if incident.event.state not in {"PENDING", "CLOSED"}:
                incident.event.state = "CLOSED"
                incident.event.closed_at = now
                incident.event.last_updated = now
                transitions.append(IncidentTransition("closed", incident.event))
        return transitions

    def rollback_open(self, event_id: str) -> None:
        """Restore PENDING when persistence of an OPEN transition rolls back."""
        for incident in self._incidents.values():
            if incident.event.event_id == event_id and incident.event.state == "OPEN":
                incident.event.state = "PENDING"
                incident.event.opened_at = None
                incident.event.last_updated = None
                incident.last_persisted = 0.0
                return

    def _prune(self, now: float) -> None:
        # observe() runs per track per frame; rebuilding the incident dict on
        # every call was O(tracks x incidents). Retention is measured in
        # minutes, so pruning at most once a second loses nothing.
        if 0.0 <= now - self._last_prune < 1.0:
            return
        self._last_prune = now
        retention = max(self.cooldown_seconds * 2, 60.0)
        self._incidents = {
            key: value for key, value in self._incidents.items()
            if value.event.state != "CLOSED" or now - (value.event.closed_at or now) <= retention
        }
        self._track_keys = {}
        for key in self._incidents:
            self._track_keys.setdefault(key[0], set()).add(key)

    @property
    def active_count(self) -> int:
        return sum(1 for item in self._incidents.values() if item.event.state in {"OPEN", "ACTIVE"})
