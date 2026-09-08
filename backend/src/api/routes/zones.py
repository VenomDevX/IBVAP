"""
IBVAP — Zones API Routes
Virtual zone management endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Optional

from src.api.auth import require_auth, require_admin
from src.database.db import get_database
from src.database.repository import Repository

router = APIRouter()


class ZoneCreate(BaseModel):
    zone_id: str
    camera_id: str
    name: str
    type: str = "restricted"
    points: List[List[int]]
    color: List[int] = [255, 0, 0]
    enabled: bool = True


@router.get("")
async def list_zones(camera_id: Optional[str] = None,
                     user: dict = Depends(require_auth)):
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
        }
        for z in zones
    ]
    session.close()

    # Also include runtime zones from zone manager
    from src.api.app import get_pipeline
    pipeline = get_pipeline()
    if pipeline and not result:
        result = pipeline.zone_manager.get_all_zones()

    return result


@router.get("/{camera_id}")
async def get_camera_zones(camera_id: str, user: dict = Depends(require_auth)):
    """Get zones for a specific camera."""
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

    repo.create_zone(zone.dict())
    actor = user.get("email") or user.get("user_id") or "unknown"
    repo.create_audit_log("create_zone", actor,
                          {"zone_id": zone.zone_id, "camera_id": zone.camera_id})
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
        )
        pipeline.zone_manager.add_zone(new_zone)

    return {"message": "Zone created", "zone_id": zone.zone_id}


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
