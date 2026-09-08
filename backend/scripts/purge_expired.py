"""
purge_expired.py — enforce configs/retention.yaml.

Deletes DB rows past their retention window and removes snapshot files that no
alert references any more. Run from cron / a scheduled task.

  python scripts/purge_expired.py --dry-run
  python scripts/purge_expired.py
"""

import argparse
import os
import sys
from datetime import datetime, timedelta

import yaml

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.database.db import get_database
from src.database.repository import Repository
from src.database.models import (
    AlertModel, EventModel, TrackModel, IdentityResultModel, ANPRResultModel, AuditLogModel,
)

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
CFG = os.path.join(BACKEND, "configs", "retention.yaml")

MODELS = {
    "events": (EventModel, "timestamp"),
    "alerts": (AlertModel, "timestamp"),
    "tracks": (TrackModel, "start_time"),
    "identity_results": (IdentityResultModel, "timestamp"),
    "anpr_results": (ANPRResultModel, "timestamp"),
    "audit_logs": (AuditLogModel, "timestamp"),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--config", default=CFG)
    args = ap.parse_args()

    days = yaml.safe_load(open(args.config, encoding="utf-8"))["retention_days"]
    now = datetime.utcnow()
    session = get_database().get_session()
    repo = Repository(session)

    try:
        for name, (model, field) in MODELS.items():
            d = days.get(name)
            if not d:
                continue
            cutoff = now - timedelta(days=d)
            q = session.query(model).filter(getattr(model, field) < cutoff)
            n = q.count()
            print(f"{name:18s} older than {d}d ({cutoff:%Y-%m-%d}): {n} rows")
            if n and not args.dry_run:
                q.delete(synchronize_session=False)
                session.commit()

        # orphaned snapshot files
        snap_dir = os.getenv("IBVAP_SNAPSHOTS_DIR", os.path.join(BACKEND, "outputs", "snapshots"))
        referenced = {
            os.path.basename(p) for (p,) in
            session.query(AlertModel.snapshot_path).filter(AlertModel.snapshot_path.isnot(None)).all()
        }
        orphans = [f for f in os.listdir(snap_dir)
                   if f.lower().endswith(".jpg") and f not in referenced] if os.path.isdir(snap_dir) else []
        print(f"orphaned snapshot files: {len(orphans)}")
        if not args.dry_run:
            for f in orphans:
                os.remove(os.path.join(snap_dir, f))
    finally:
        session.close()

    if args.dry_run:
        print("\n(dry run — nothing deleted)")


if __name__ == "__main__":
    main()
