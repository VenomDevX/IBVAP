"""
IBVAP — Track Manager
High-level track lifecycle management and querying.
"""

import time
from collections import deque

from src.tracking.track import Track


class TrackManager:
    """
    Manages track lifecycle — creation, updates, expiration, querying.
    Works on top of the raw tracker output.
    """

    def __init__(self, expiry_seconds: float = 10.0):
        self.expiry_seconds = expiry_seconds
        self._tracks: dict[int, Track] = {}
        self._expired_tracks = deque(maxlen=1000)
        # Keyed by track_uuid: numeric ByteTrack ids restart after a tracker
        # reset, so they would wrongly mark a brand-new track as already expired.
        self._expired_ids: set[str] = set()

    def update_tracks(self, active_tracks: dict[int, Track]):
        """Sync internal state with tracker output."""
        now = time.time()
        # Merge instead of replacing the registry with only ByteTrack's active
        # output. Replacing it made LOST/CLOSED lifecycle processing impossible.
        self._tracks.update(active_tracks)

        # Find expired tracks
        for tid in list(self._tracks.keys()):
            track = self._tracks[tid]
            if not track.is_active or (now - track.last_seen) > self.expiry_seconds:
                track.is_active = False
                track.status = "CLOSED" if (now - track.last_seen) > self.expiry_seconds else "LOST"
                if track.track_uuid not in self._expired_ids:
                    self._expired_ids.add(track.track_uuid)
                    self._expired_tracks.append(track)
                if track.status == "CLOSED" and tid not in active_tracks:
                    # Closed tracks live on only in the bounded expired deque.
                    del self._tracks[tid]
        if len(self._expired_ids) > 5000:
            self._expired_ids = {t.track_uuid for t in self._expired_tracks}

    def get_active_tracks(self) -> dict[int, Track]:
        """Get all currently active tracks."""
        now = time.time()
        return {
            tid: t
            for tid, t in self._tracks.items()
            if t.is_active and t.status in {"NEW", "ACTIVE"} and now - t.last_seen <= self.expiry_seconds
        }

    def get_track(self, track_id: int) -> Track | None:
        return self._tracks.get(track_id)

    def get_tracks_in_zone(self, zone_id: str) -> list[Track]:
        """Get all active tracks currently inside a zone."""
        return [t for t in self._tracks.values() if t.is_active and zone_id in t.current_zones]

    def get_person_tracks(self) -> dict[int, Track]:
        return {tid: t for tid, t in self._tracks.items() if t.is_active and t.object_type == "person"}

    def get_vehicle_tracks(self) -> dict[int, Track]:
        vehicle_types = {"car", "motorcycle", "bus", "truck", "night_vision_object"}
        return {tid: t for tid, t in self._tracks.items() if t.is_active and t.object_type in vehicle_types}

    def get_loitering_tracks(self) -> list[Track]:
        return [t for t in self._tracks.values() if t.is_active and t.is_loitering]

    def get_recent_expired(self, limit: int = 50) -> list[Track]:
        return list(self._expired_tracks)[-limit:]

    @property
    def active_count(self) -> int:
        return len(self.get_active_tracks())

    @property
    def person_count(self) -> int:
        return len(self.get_person_tracks())

    @property
    def vehicle_count(self) -> int:
        return len(self.get_vehicle_tracks())

    def get_statistics(self) -> dict:
        return {
            "active_tracks": self.active_count,
            "person_count": self.person_count,
            "vehicle_count": self.vehicle_count,
            "total_tracks_seen": len(self._tracks) + len(self._expired_tracks),
            "loitering_count": len(self.get_loitering_tracks()),
        }
