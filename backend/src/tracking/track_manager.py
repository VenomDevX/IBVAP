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
        self._expired_ids: set = set()

    def update_tracks(self, active_tracks: dict[int, Track]):
        """Sync internal state with tracker output."""
        now = time.time()
        self._tracks = active_tracks

        # Find expired tracks
        for tid in list(self._tracks.keys()):
            track = self._tracks[tid]
            if not track.is_active or (now - track.last_seen) > self.expiry_seconds:
                track.is_active = False
                if tid not in self._expired_ids:
                    self._expired_ids.add(tid)
                    self._expired_tracks.append(track)
        if len(self._expired_ids) > 5000:
            self._expired_ids = {t.track_id for t in self._expired_tracks}

    def get_active_tracks(self) -> dict[int, Track]:
        """Get all currently active tracks."""
        return {tid: t for tid, t in self._tracks.items() if t.is_active}

    def get_track(self, track_id: int) -> Track | None:
        return self._tracks.get(track_id)

    def get_tracks_in_zone(self, zone_id: str) -> list[Track]:
        """Get all active tracks currently inside a zone."""
        return [t for t in self._tracks.values() if t.is_active and zone_id in t.current_zones]

    def get_person_tracks(self) -> dict[int, Track]:
        return {tid: t for tid, t in self._tracks.items() if t.is_active and t.object_type == "person"}

    def get_vehicle_tracks(self) -> dict[int, Track]:
        vehicle_types = {"car", "motorcycle", "bus", "truck"}
        return {tid: t for tid, t in self._tracks.items() if t.is_active and t.object_type in vehicle_types}

    def get_loitering_tracks(self) -> list[Track]:
        return [t for t in self._tracks.values() if t.is_active and t.is_loitering]

    def get_recent_expired(self, limit: int = 50) -> list[Track]:
        return list(self._expired_tracks)[-limit:]

    @property
    def active_count(self) -> int:
        return sum(1 for t in self._tracks.values() if t.is_active)

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
