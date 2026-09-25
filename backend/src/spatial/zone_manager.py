"""
IBVAP — Zone Manager
Manages virtual restricted zones with polygon-based containment checks.
"""

from dataclasses import dataclass, field
from typing import Any

import cv2
import numpy as np
from loguru import logger

try:
    from shapely.geometry import Point, Polygon
except ImportError:
    Point = None
    Polygon = None
    logger.warning("shapely not installed — zone checks will use OpenCV fallback")


@dataclass
class Zone:
    """A virtual zone definition."""

    zone_id: str
    name: str
    zone_type: str  # "restricted", "buffer", "safe", "entry_exit"
    camera_id: str
    points: list[tuple[int, int]]
    enabled: bool = True
    color: tuple[int, int, int] = (255, 0, 0)
    # Object classes this zone reacts to; empty = every class.
    trigger_classes: list[str] = field(default_factory=list)
    _polygon: Any = field(default=None, repr=False)

    def __post_init__(self):
        if Polygon is not None and len(self.points) >= 3:
            self._polygon = Polygon(self.points)

    def applies_to(self, object_type: str | None) -> bool:
        return not self.trigger_classes or object_type is None or object_type in self.trigger_classes

    def contains_point(self, x: int, y: int) -> bool:
        """Check if a point is inside this zone."""
        if not self.enabled:
            return False

        if self._polygon is not None:
            return self._polygon.contains(Point(x, y))
        else:
            # OpenCV fallback
            pts = np.array(self.points, dtype=np.int32)
            result = cv2.pointPolygonTest(pts, (float(x), float(y)), False)
            return result >= 0

    def distance_to_boundary(self, x: int, y: int) -> float:
        """Get signed distance from point to zone boundary.
        Negative = inside, Positive = outside.
        """
        if self._polygon is not None:
            point = Point(x, y)
            dist = self._polygon.exterior.distance(point)
            if self._polygon.contains(point):
                return -dist
            return dist
        else:
            pts = np.array(self.points, dtype=np.int32)
            return cv2.pointPolygonTest(pts, (float(x), float(y)), True)

    def to_dict(self) -> dict:
        return {
            "zone_id": self.zone_id,
            "name": self.name,
            "type": self.zone_type,
            "camera_id": self.camera_id,
            "points": self.points,
            "enabled": self.enabled,
            "color": list(self.color),
            "trigger_classes": list(self.trigger_classes),
        }


class ZoneManager:
    """
    Manages all virtual zones across cameras.
    Provides containment checks and zone visualization.
    """

    def __init__(self):
        self._zones: dict[str, Zone] = {}  # zone_id -> Zone
        self._camera_zones: dict[str, list[str]] = {}  # camera_id -> [zone_ids]

    def load_from_config(self, config: dict):
        """Load zones from YAML config."""
        zones_config = config.get("zones", {})

        for camera_id, camera_zones in zones_config.items():
            for zone_cfg in camera_zones:
                zone = Zone(
                    zone_id=zone_cfg["id"],
                    name=zone_cfg["name"],
                    zone_type=zone_cfg["type"],
                    camera_id=camera_id,
                    points=[tuple(p) for p in zone_cfg["points"]],
                    enabled=zone_cfg.get("enabled", True),
                    color=tuple(zone_cfg.get("color", [255, 0, 0])),
                    trigger_classes=list(zone_cfg.get("trigger_classes") or []),
                )
                self.add_zone(zone)
                logger.info(f"Loaded zone: {zone.name} ({zone.zone_type}) for {camera_id}")

    def add_zone(self, zone: Zone):
        """Add a zone to the manager."""
        self._zones[zone.zone_id] = zone
        if zone.camera_id not in self._camera_zones:
            self._camera_zones[zone.camera_id] = []
        if zone.zone_id not in self._camera_zones[zone.camera_id]:
            self._camera_zones[zone.camera_id].append(zone.zone_id)

    def remove_zone(self, zone_id: str):
        """Remove a zone."""
        if zone_id in self._zones:
            zone = self._zones[zone_id]
            if zone.camera_id in self._camera_zones:
                self._camera_zones[zone.camera_id] = [z for z in self._camera_zones[zone.camera_id] if z != zone_id]
            del self._zones[zone_id]

    def get_zone(self, zone_id: str) -> Zone | None:
        return self._zones.get(zone_id)

    def get_camera_zones(self, camera_id: str) -> list[Zone]:
        """Get all zones for a specific camera."""
        zone_ids = self._camera_zones.get(camera_id, [])
        return [self._zones[zid] for zid in zone_ids if zid in self._zones]

    def check_point(self, camera_id: str, x: int, y: int, object_type: str | None = None) -> list[Zone]:
        """
        Check which zones a point falls inside for a given camera.
        Returns the zones the point is in, limited to zones that apply to object_type.
        """
        containing_zones = []
        for zone in self.get_camera_zones(camera_id):
            if zone.enabled and zone.applies_to(object_type) and zone.contains_point(x, y):
                containing_zones.append(zone)
        return containing_zones

    def check_track_zones(self, camera_id: str, centroid: tuple[int, int], object_type: str | None = None) -> list[str]:
        """
        Check which zone IDs a tracked object's centroid falls inside.
        Returns list of zone IDs.
        """
        x, y = centroid
        zones = self.check_point(camera_id, x, y, object_type)
        return [z.zone_id for z in zones]

    def is_in_restricted_zone(self, camera_id: str, x: int, y: int, object_type: str | None = None) -> bool:
        """Quick check if a point is in any restricted zone that applies to object_type."""
        for zone in self.get_camera_zones(camera_id):
            if (
                zone.enabled
                and zone.zone_type == "restricted"
                and zone.applies_to(object_type)
                and zone.contains_point(x, y)
            ):
                return True
        return False

    def get_nearest_zone_distance(
        self, camera_id: str, x: int, y: int, zone_type: str = "restricted"
    ) -> tuple[str | None, float]:
        """Get distance to the nearest zone of a given type."""
        min_dist = float("inf")
        nearest_id = None

        for zone in self.get_camera_zones(camera_id):
            if zone.zone_type == zone_type and zone.enabled:
                dist = zone.distance_to_boundary(x, y)
                abs_dist = abs(dist)
                if abs_dist < min_dist:
                    min_dist = abs_dist
                    nearest_id = zone.zone_id

        return nearest_id, min_dist if nearest_id else float("inf")

    @staticmethod
    def draw_zones(frame: np.ndarray, zones: list[Zone], alpha: float = 0.3) -> np.ndarray:
        """Draw zone overlays on frame."""
        overlay = frame.copy()

        for zone in zones:
            if not zone.enabled:
                continue

            pts = np.array(zone.points, dtype=np.int32).reshape((-1, 1, 2))

            # Filled polygon overlay
            cv2.fillPoly(overlay, [pts], zone.color)

            # Border
            cv2.polylines(frame, [pts], True, zone.color, 2)

            # Label
            cx = int(np.mean([p[0] for p in zone.points]))
            cy = int(np.mean([p[1] for p in zone.points]))
            label = f"{zone.name} ({zone.zone_type})"
            cv2.putText(frame, label, (cx - 50, cy), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)

        # Blend overlay
        result = cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0)
        return result

    def get_all_zones(self) -> list[dict]:
        """Get all zones as JSON-serializable list."""
        return [zone.to_dict() for zone in self._zones.values()]
