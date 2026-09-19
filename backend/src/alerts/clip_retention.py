"""
IBVAP — Evidence clip retention.

Deletes pre/post-event clips older than a number of days, plus clip files no
event references, and drops the matching event_evidence rows (not
hash-chained). Used by scripts/purge_expired.py and the settings screen.
"""

import os
from datetime import datetime, timedelta

from src.alerts.evidence_clip import EvidenceClipBuffer
from src.database.models import EventEvidenceModel


def clip_usage(clip_dir: str) -> dict:
    files = size = 0
    if os.path.isdir(clip_dir):
        with os.scandir(clip_dir) as entries:
            for entry in entries:
                if entry.is_file() and entry.name.lower().endswith(".avi"):
                    files += 1
                    size += entry.stat().st_size
    return {"files": files, "bytes": size}


def purge_clips(session, clip_dir: str, older_than_days: int | None, now: datetime, dry_run: bool) -> dict:
    """Returns {"files", "bytes"} removed (or that would be removed on a dry run)."""
    if not os.path.isdir(clip_dir):
        return {"files": 0, "bytes": 0}
    rows = session.query(EventEvidenceModel).filter(EventEvidenceModel.clip_path.isnot(None)).all()
    by_name: dict[str, list] = {}
    for row in rows:
        by_name.setdefault(os.path.basename(row.clip_path), []).append(row)
    cutoff = (now - timedelta(days=older_than_days)).timestamp() if older_than_days else None

    expired, orphans, size = [], [], 0
    with os.scandir(clip_dir) as entries:
        for entry in entries:
            if not entry.is_file() or not entry.name.lower().endswith(".avi"):
                continue
            stat = entry.stat()
            if entry.name not in by_name:
                orphans.append(entry.name)
            elif cutoff is not None and stat.st_mtime < cutoff:
                expired.append(entry.name)
            else:
                continue
            size += stat.st_size
    result = {"files": len(expired) + len(orphans), "bytes": size}
    if dry_run or not result["files"]:
        return result

    for name in expired + orphans:
        try:
            os.remove(os.path.join(clip_dir, name))
        except FileNotFoundError:
            pass
    for name in expired:
        for row in by_name[name]:
            session.delete(row)
    session.commit()
    EvidenceClipBuffer.refresh_store(clip_dir)
    return result
