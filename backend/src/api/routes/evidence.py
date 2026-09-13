"""Authorized event evidence metadata and download."""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from src.api.auth import require_auth, require_camera_access
from src.database.db import get_database
from src.database.repository import Repository
from src.paths import output_dir, snapshots_dir

router = APIRouter()


def _serialize(row) -> dict:
    return {
        "evidence_id": row.id, "event_id": row.event_id, "type": row.evidence_type,
        "created_at": row.created_at.isoformat(),
        "download_url": f"/api/v1/evidence/{row.event_id}/{row.id}",
    }


@router.get("/{event_id}")
async def list_evidence(event_id: str, user: dict = Depends(require_auth)):
    with get_database().get_session() as session:
        repo = Repository(session)
        event = repo.get_event(event_id)
        if event is None:
            raise HTTPException(status_code=404, detail="Event not found")
        require_camera_access(user, event.camera_id)
        return [_serialize(row) for row in repo.get_event_evidence(event_id)]


@router.get("/{event_id}/{evidence_id}")
async def download_evidence(event_id: str, evidence_id: int, user: dict = Depends(require_auth)):
    with get_database().get_session() as session:
        repo = Repository(session)
        event = repo.get_event(event_id)
        if event is None:
            raise HTTPException(status_code=404, detail="Event not found")
        require_camera_access(user, event.camera_id)
        row = next((item for item in repo.get_event_evidence(event_id) if item.id == evidence_id), None)
        if row is None:
            raise HTTPException(status_code=404, detail="Evidence not found")
        raw_path = row.clip_path or row.snapshot_path
        if not raw_path:
            raise HTTPException(status_code=404, detail="Evidence file unavailable")
        path = Path(raw_path).resolve()
        roots = (output_dir().resolve(), snapshots_dir().resolve())
        if not any(path.is_relative_to(root) for root in roots) or not path.is_file():
            raise HTTPException(status_code=404, detail="Evidence file unavailable")
        media_type = "video/x-msvideo" if path.suffix.lower() == ".avi" else "image/jpeg"
        return FileResponse(path, media_type=media_type, filename=path.name)
