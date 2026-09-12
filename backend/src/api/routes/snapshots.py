"""
IBVAP — Evidence Snapshot Routes
Authenticated, path-confined access to evidence images.

Replaces the old unauthenticated `StaticFiles` mount at /snapshots — those files
are annotated frames of real people/vehicles/plates from surveillance cameras and
must not be world-readable or cacheable by intermediaries.
"""

import os
import re

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse

from src.api.auth import can_access_camera, require_auth_media
from src.api.ratelimit import limiter
from src.database.db import get_database
from src.database.repository import Repository

router = APIRouter()

_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+\.(jpg|jpeg|png)$", re.IGNORECASE)


def _snapshots_dir() -> str:
    return os.path.realpath(os.getenv("IBVAP_SNAPSHOTS_DIR", "./outputs/snapshots"))


@router.get("/{name}")
@limiter.limit("120/minute")
async def get_snapshot(name: str, request: Request, _user: dict = Depends(require_auth_media)):
    """Serve one evidence image by filename (no traversal, no listing)."""
    if not _NAME_RE.match(name):
        raise HTTPException(status_code=400, detail="Invalid snapshot name")

    base = _snapshots_dir()
    target = os.path.realpath(os.path.join(base, name))
    if os.path.commonpath([base, target]) != base or not os.path.isfile(target):
        raise HTTPException(status_code=404, detail="Snapshot not found")

    with get_database().get_session() as session:
        owners = Repository(session).get_snapshot_cameras(name)
    if not owners or any(not can_access_camera(_user, cam) for cam in owners):
        raise HTTPException(status_code=403, detail="Evidence access denied")

    return FileResponse(
        target,
        media_type="image/jpeg",
        headers={"Cache-Control": "private, no-store"},
    )
