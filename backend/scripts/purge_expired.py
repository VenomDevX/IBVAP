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

from src.alerts.evidence_chain import CHAINED, purge_chained_prefix
from src.database.db import get_database
from src.database.models import (
    AlertModel,
    ANPRResultModel,
    AuditLogModel,
    IdentityResultModel,
    TrackModel,
)
from src.paths import snapshots_dir

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
CFG = os.path.join(BACKEND, "configs", "retention.yaml")

MODELS = {
    # Child rows must be removed before their parents now that SQLite foreign
    # keys are enforced on every connection. "alerts" and "events" are
    # hash-chained: purge_chained_prefix trims them without breaking the chain.
    "alerts": None,
    "identity_results": (IdentityResultModel, "timestamp"),
    "anpr_results": (ANPRResultModel, "timestamp"),
    "tracks": (TrackModel, "start_time"),
    "events": None,
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

    try:
        for name, spec in MODELS.items():
            d = days.get(name)
            if not d:
                continue
            cutoff = now - timedelta(days=d)
            if name in CHAINED:
                n = purge_chained_prefix(session, name, cutoff, dry_run=args.dry_run)
                print(f"{name:18s} older than {d}d ({cutoff:%Y-%m-%d}): {n} rows (chain-safe prefix)")
                continue
            model, field = spec
            q = session.query(model).filter(getattr(model, field) < cutoff)
            n = q.count()
            print(f"{name:18s} older than {d}d ({cutoff:%Y-%m-%d}): {n} rows")
            if n and not args.dry_run:
                q.delete(synchronize_session=False)
                session.commit()

        # Enforce the snapshot window independently from alert-row retention,
        # then also remove any unreferenced evidence regardless of age.
        snap_dir = str(snapshots_dir())
        referenced = {
            os.path.basename(p)
            for (p,) in session.query(AlertModel.snapshot_path).filter(AlertModel.snapshot_path.isnot(None)).all()
        }
        snapshot_days = days.get("snapshots")
        snapshot_cutoff = (now - timedelta(days=snapshot_days)).timestamp() if snapshot_days else None
        candidates = (
            [f for f in os.listdir(snap_dir) if f.lower().endswith((".jpg", ".jpeg", ".png"))]
            if os.path.isdir(snap_dir)
            else []
        )
        expired = [
            f for f in candidates
            if snapshot_cutoff is not None and os.path.getmtime(os.path.join(snap_dir, f)) < snapshot_cutoff
        ]
        orphans = [f for f in candidates if f not in referenced]
        removable = sorted(set(expired) | set(orphans))
        print(f"expired snapshot files: {len(expired)}")
        print(f"orphaned snapshot files: {len(orphans)}")
        print(f"snapshot files to remove: {len(removable)}")
        if not args.dry_run:
            for f in removable:
                os.remove(os.path.join(snap_dir, f))
            # The alert keeps its snapshot_hash (it is part of the chain); only the
            # dangling path is cleared so verification doesn't report a missing file.
            removed = set(removable)
            for alert in session.query(AlertModel).filter(AlertModel.snapshot_path.isnot(None)).all():
                if os.path.basename(alert.snapshot_path) in removed:
                    alert.snapshot_path = None
            session.commit()
    finally:
        session.close()

    if args.dry_run:
        print("\n(dry run — nothing deleted)")


if __name__ == "__main__":
    main()
