"""
IBVAP — Zones API Routes
Virtual zone management endpoints.
"""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from shapely.geometry import Polygon

from src.api.auth import can_access_camera, require_admin, require_auth, require_camera_access
from src.database.db import get_database
from src.database.repository import Repository

router = APIRouter()

TriggerClass = Annotated[str, Field(min_length=1, max_length=50, pattern=r"^[a-z0-9_]+$")]


class ZoneCreate(BaseModel):
    zone_id: str = Field(min_length=1, max_length=50, pattern=r"^[A-Za-z0-9_-]+$")
    camera_id: str = Field(min_length=1, max_length=50, pattern=r"^[A-Za-z0-9_-]+$")
    name: str = Field(min_length=1, max_length=200)
    type: Literal["restricted", "buffer", "safe", "entry_exit"] = "restricted"
    points: list[tuple[int, int]] = Field(min_length=3, max_length=256)
    color: tuple[int, int, int] = (255, 0, 0)
    enabled: bool = True
    trigger_classes: list[TriggerClass] = Field(default_factory=list, max_length=32)

    @field_validator("points")
    @classmethod
    def valid_polygon(cls, points):
        polygon = Polygon(points)
        if not polygon.is_valid or polygon.area == 0 or any(x < 0 or y < 0 for x, y in points):
            raise ValueError("Zone must be a valid nonzero polygon with nonnegative coordinates")
        return points

    @field_validator("color")
    @classmethod
    def valid_color(cls, color):
        if any(c < 0 or c > 255 for c in color):
            raise ValueError("Color channels must be between 0 and 255")
        return color


class ZoneUpdate(BaseModel):
    camera_id: str | None = Field(default=None, min_length=1, max_length=50, pattern=r"^[A-Za-z0-9_-]+$")
    name: str | None = Field(default=None, min_length=1, max_length=200)
    type: Literal["restricted", "buffer", "safe", "entry_exit"] | None = None
    points: list[tuple[int, int]] | None = Field(default=None, min_length=3, max_length=256)
    color: tuple[int, int, int] | None = None
    enabled: bool | None = None
    trigger_classes: list[TriggerClass] | None = Field(default=None, max_length=32)

    @field_validator("points")
    @classmethod
    def valid_polygon(cls, points):
        if points is None:
            return points
        polygon = Polygon(points)
        if not polygon.is_valid or polygon.area == 0 or any(x < 0 or y < 0 for x, y in points):
            raise ValueError("Zone must be a valid nonzero polygon with nonnegative coordinates")
        return points

    @field_validator("color")
    @classmethod
    def valid_color(cls, color):
        if color is not None and any(c < 0 or c > 255 for c in color):
            raise ValueError("Color channels must be between 0 and 255")
        return color


@router.get("")
async def list_zones(camera_id: str | None = None, user: dict = Depends(require_auth)):
    """Get all zones, optionally filtered by camera."""
    db = get_database()
    session = db.get_session()
    repo = Repository(session)
    zones = repo.get_zones(camera_id)
    result = [
        {
            "zone_id": z.zone_id,
            "camera_id": z.camera_id,
            "name": z.name,
            "type": z.zone_type,
            "points": z.points,
            "color": z.color,
            "enabled": z.enabled,
            "trigger_classes": list(z.trigger_classes or []),
        }
        for z in zones if can_access_camera(user, z.camera_id)
    ]
    session.close()

    return result


@router.get("/{camera_id}")
async def get_camera_zones(camera_id: str, user: dict = Depends(require_auth)):
    """Get zones for a specific camera."""
    require_camera_access(user, camera_id)
    from src.api.app import get_pipeline

    pipeline = get_pipeline()
    if pipeline:
        zones = pipeline.zone_manager.get_camera_zones(camera_id)
        return [z.to_dict() for z in zones]
    return []


@router.post("")
async def create_zone(zone: ZoneCreate, user: dict = Depends(require_admin)):
    """Create a new virtual zone (admin only)."""
    db = get_database()
    session = db.get_session()
    repo = Repository(session)

    if any(z.zone_id == zone.zone_id for z in repo.get_zones(include_deleted=True)):
        session.close()
        raise HTTPException(status_code=409, detail="Zone ID already exists")
    repo.create_zone(zone.model_dump())
    actor = user.get("email") or user.get("user_id") or "unknown"
    repo.create_audit_log("create_zone", actor, {"zone_id": zone.zone_id, "camera_id": zone.camera_id})
    session.close()

    # Add to runtime zone manager
    from src.api.app import get_pipeline
    from src.spatial.zone_manager import Zone

    pipeline = get_pipeline()
    if pipeline:
        new_zone = Zone(
            zone_id=zone.zone_id,
            name=zone.name,
            zone_type=zone.type,
            camera_id=zone.camera_id,
            points=[tuple(p) for p in zone.points],
            enabled=zone.enabled,
            color=tuple(zone.color),
            trigger_classes=list(zone.trigger_classes),
        )
        pipeline.zone_manager.add_zone(new_zone)

    return {"message": "Zone created", "zone_id": zone.zone_id}


@router.patch("/{zone_id}")
async def update_zone(zone_id: str, update: ZoneUpdate, user: dict = Depends(require_admin)):
    """Edit geometry, assignment, type or enabled state of a zone."""
    session = get_database().get_session()
    try:
        repo = Repository(session)
        changes = update.model_dump(exclude_unset=True)
        if "points" in changes and changes["points"] is not None:
            changes["points"] = [list(point) for point in changes["points"]]
        if "color" in changes and changes["color"] is not None:
            changes["color"] = list(changes["color"])
        existing = next((z for z in repo.get_zones() if z.zone_id == zone_id), None)
        field_map = {"camera_id": "camera_id", "name": "name", "type": "zone_type", "points": "points",
                     "color": "color", "enabled": "enabled", "trigger_classes": "trigger_classes"}
        before = {f: getattr(existing, field_map[f], None) for f in changes} if existing else {}
        row = repo.update_zone(zone_id, changes)
        if row is None:
            raise HTTPException(status_code=404, detail="Zone not found")
        actor = user.get("email") or user.get("user_id") or "unknown"
        diff = {
            f: ({"from": "(shape)", "to": "(new shape)"} if f == "points" else {"from": before.get(f), "to": v})
            for f, v in changes.items() if before.get(f) != v
        }
        if set(diff) == {"enabled"}:
            action = "enable_zone" if changes["enabled"] else "disable_zone"
            repo.create_audit_log(action, actor, {"zone_id": zone_id, "name": row.name})
        elif diff:
            repo.create_audit_log("update_zone", actor, {"zone_id": zone_id, "name": row.name, "changes": diff})

        from src.api.app import get_pipeline
        from src.spatial.zone_manager import Zone
        pipeline = get_pipeline()
        if pipeline:
            pipeline.zone_manager.remove_zone(zone_id)
            pipeline.zone_manager.add_zone(Zone(
                zone_id=row.zone_id, name=row.name, zone_type=row.zone_type,
                camera_id=row.camera_id, points=[tuple(point) for point in row.points],
                enabled=row.enabled, color=tuple(row.color),
                trigger_classes=list(row.trigger_classes or []),
            ))
        return {"message": "Zone updated", "zone_id": zone_id}
    finally:
        session.close()


@router.delete("/{zone_id}")
async def delete_zone(zone_id: str, user: dict = Depends(require_admin)):
    """Delete a virtual zone (admin only)."""
    db = get_database()
    session = db.get_session()
    repo = Repository(session)
    success = repo.delete_zone(zone_id)
    actor = user.get("email") or user.get("user_id") or "unknown"
    repo.create_audit_log("delete_zone", actor, {"zone_id": zone_id})
    session.close()

    from src.api.app import get_pipeline

    pipeline = get_pipeline()
    if pipeline:
        pipeline.zone_manager.remove_zone(zone_id)

    if not success:
        raise HTTPException(status_code=404, detail="Zone not found")

    return {"message": "Zone deleted", "zone_id": zone_id}
