"""
IBVAP — Evidence storage API

Clip disk usage for the settings screen, and an admin action to delete clips
older than N days (always audit-logged; supports a dry-run preview).
"""

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from src.alerts.clip_retention import clip_usage, purge_clips
from src.api.auth import require_admin, require_auth
from src.database.db import get_database
from src.database.repository import Repository
from src.paths import output_dir

router = APIRouter()
MB = 1024 * 1024


def clip_dir() -> str:
    return str(output_dir() / "clips")


def _clip_limit_mb() -> float | None:
    from src.api.app import get_pipeline

    pipeline = get_pipeline()
    for camera in getattr(pipeline, "camera_pipelines", {}).values():
        buffer = getattr(camera, "evidence_buffer", None)
        if buffer is not None:
            return round(buffer.max_storage_bytes / MB)
    return None


class PurgeRequest(BaseModel):
    older_than_days: int = Field(ge=1, le=3650)
    dry_run: bool = False


@router.get("/clips")
def clip_storage(user: dict = Depends(require_auth)):
    usage = clip_usage(clip_dir())
    limit = _clip_limit_mb()
    used_mb = round(usage["bytes"] / MB, 1)
    return {
        "files": usage["files"],
        "used_mb": used_mb,
        "limit_mb": limit,
        "recording": limit is None or used_mb < limit,
    }


@router.post("/clips/purge")
def purge_old_clips(request: PurgeRequest, user: dict = Depends(require_admin)):
    with get_database().get_session() as session:
        result = purge_clips(session, clip_dir(), request.older_than_days, datetime.utcnow(), request.dry_run)
        if not request.dry_run:
            Repository(session).create_audit_log(
                "purge_clips",
                user.get("email") or user.get("user_id") or "unknown",
                {"older_than_days": request.older_than_days, "files": result["files"], "bytes": result["bytes"]},
            )
    return {
        "files": result["files"],
        "freed_bytes": result["bytes"],
        "freed_mb": round(result["bytes"] / MB, 1),
        "dry_run": request.dry_run,
    }
