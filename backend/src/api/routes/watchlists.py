"""
IBVAP — Watchlist API Routes

Enrol faces and number plates as wanted / authorized / VIP. Face photos are
never stored: only the ArcFace embedding, encrypted at rest.
"""

from typing import Literal

import cv2
import numpy as np
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from src.api.auth import require_role
from src.api.middleware.input_validator import validate_image_file
from src.database.db import get_database
from src.database.repository import Repository
from src.watchlist.crypto import WatchlistKeyError
from src.watchlist.service import get_watchlist, reload_watchlist

router = APIRouter()

MAX_FACE_IMAGE_BYTES = 8 * 1024 * 1024
ListType = Literal["wanted", "authorized", "vip"]

can_view = require_role("commander", "supervisor", "operator", "auditor")
can_edit = require_role("commander", "supervisor")


class PlateEntry(BaseModel):
    plate: str = Field(min_length=4, max_length=30, pattern=r"^[A-Za-z0-9 \-]+$")
    list_type: ListType = "wanted"
    label: str = Field(min_length=1, max_length=200)
    notes: str = Field(default="", max_length=1000)


def _actor(user: dict) -> str:
    return user.get("email") or user.get("user_id") or "unknown"


def _entry_dict(row) -> dict:
    return {
        "entry_id": row.entry_id,
        "kind": row.kind,
        "list_type": row.list_type,
        "label": row.label,
        "plate": row.plate,
        "notes": row.notes,
        "active": row.active,
        "created_by": row.created_by,
        "created_at": row.created_at.isoformat() + "Z" if row.created_at else None,
        "deactivated_by": row.deactivated_by,
        "deactivated_at": row.deactivated_at.isoformat() + "Z" if row.deactivated_at else None,
    }


@router.get("")
async def list_entries(
    kind: Literal["face", "plate"] | None = None,
    include_inactive: bool = Query(default=False),
    user: dict = Depends(can_view),
):
    with get_database().get_session() as session:
        rows = Repository(session).list_watchlist_entries(kind=kind, include_inactive=include_inactive)
        return {"entries": [_entry_dict(r) for r in rows], "loaded": get_watchlist().size}


@router.post("/plates", status_code=201)
async def add_plate(entry: PlateEntry, user: dict = Depends(can_edit)):
    with get_database().get_session() as session:
        repo = Repository(session)
        try:
            row = repo.create_watchlist_entry(
                kind="plate", list_type=entry.list_type, label=entry.label.strip(),
                plate=entry.plate, notes=entry.notes, created_by=_actor(user),
            )
        except ValueError as exc:
            raise HTTPException(status_code=409 if "already" in str(exc) else 422, detail=str(exc)) from exc
        repo.create_audit_log("watchlist_add", _actor(user), {
            "entry_id": row.entry_id, "kind": "plate", "list_type": row.list_type, "plate": row.plate,
        })
        result = _entry_dict(row)
    reload_watchlist()
    return result


@router.post("/faces", status_code=201)
async def add_face(
    image: UploadFile = File(...),
    label: str = Form(..., min_length=1, max_length=200),
    list_type: ListType = Form("wanted"),
    notes: str = Form("", max_length=1000),
    user: dict = Depends(can_edit),
):
    from src.api.app import get_pipeline

    pipeline = get_pipeline()
    recognizer = getattr(pipeline, "face_recognizer", None)
    if recognizer is None or not recognizer.active:
        raise HTTPException(status_code=503, detail="Face recognition is not running (face.enabled / insightface)")

    content = await image.read(MAX_FACE_IMAGE_BYTES + 1)
    if len(content) > MAX_FACE_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="Image larger than 8 MB")
    ok, err = validate_image_file(content, image.filename or "")
    if not ok:
        raise HTTPException(status_code=400, detail=err)
    frame = cv2.imdecode(np.frombuffer(content, np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        raise HTTPException(status_code=400, detail="Image could not be decoded")

    faces = recognizer.faces(frame)
    if not faces:
        raise HTTPException(status_code=422, detail="No clear face found in the image")
    if len(faces) > 1:
        raise HTTPException(status_code=422, detail="More than one face in the image; crop to one person")

    with get_database().get_session() as session:
        repo = Repository(session)
        try:
            row = repo.create_watchlist_entry(
                kind="face", list_type=list_type, label=label.strip(), notes=notes,
                embedding=faces[0]["embedding"], created_by=_actor(user),
            )
        except WatchlistKeyError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        repo.create_audit_log("watchlist_add", _actor(user), {
            "entry_id": row.entry_id, "kind": "face", "list_type": row.list_type,
        })
        result = _entry_dict(row)
    reload_watchlist()
    return result


@router.delete("/{entry_id}")
async def deactivate_entry(entry_id: str, user: dict = Depends(can_edit)):
    with get_database().get_session() as session:
        repo = Repository(session)
        if not repo.deactivate_watchlist_entry(entry_id, actor=_actor(user)):
            raise HTTPException(status_code=404, detail="No active watchlist entry with that id")
        repo.create_audit_log("watchlist_remove", _actor(user), {"entry_id": entry_id})
    reload_watchlist()
    return {"message": "Watchlist entry deactivated", "entry_id": entry_id}
