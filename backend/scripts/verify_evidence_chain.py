"""
verify_evidence_chain.py — check the alert/event tamper-evident hash chain.

Walks each table in insert order, recomputes the HMAC chain, and reports the
first broken link. Also re-hashes each snapshot file and flags mismatches.

  # env: EVIDENCE_HMAC_KEY (same key used when the rows were written)
  python scripts/verify_evidence_chain.py
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.alerts import evidence
from src.database.db import get_database
from src.database.models import AlertModel, EventModel

EVENT_FIELDS = [
    "event_id",
    "camera_id",
    "track_id",
    "event_type",
    "timestamp",
    "object_type",
    "risk_score",
    "risk_level",
    "evidence_hash",
]
ALERT_FIELDS = [
    "alert_id",
    "camera_id",
    "event_id",
    "track_id",
    "event_type",
    "timestamp",
    "risk_score",
    "risk_level",
    "object_type",
    "snapshot_hash",
]


def check(session, model, fields, label):
    rows = session.query(model).order_by(model.id).all()
    prev = None
    breaks = []
    for row in rows:
        if row.chain_hash is None:
            continue  # pre-chain row
        rec = {f: getattr(row, f) for f in fields}
        if not evidence.verify(rec, prev, row.chain_hash):
            key = getattr(row, fields[0])
            breaks.append(key)
        prev = row.chain_hash
    status = "OK" if not breaks else f"BROKEN at {breaks}"
    print(f"[{label}] {len(rows)} rows  ->  {status}")
    return not breaks


def check_snapshots(session):
    bad = []
    for a in session.query(AlertModel).filter(AlertModel.snapshot_path.isnot(None)).all():
        if not a.snapshot_hash:
            continue
        actual = evidence.sha256_file(a.snapshot_path)
        if actual is None:
            bad.append(f"{a.alert_id}: file missing ({a.snapshot_path})")
        elif actual != a.snapshot_hash:
            bad.append(f"{a.alert_id}: snapshot content changed")
    if bad:
        print("[snapshots] MISMATCH:")
        for b in bad:
            print(f"   {b}")
    else:
        print("[snapshots] all present and unchanged")
    return not bad


def main():
    if not os.getenv("EVIDENCE_HMAC_KEY"):
        print("WARNING: EVIDENCE_HMAC_KEY not set — cannot verify rows written in another run.\n")
    session = get_database().get_session()
    try:
        ok = check(session, EventModel, EVENT_FIELDS, "events")
        ok &= check(session, AlertModel, ALERT_FIELDS, "alerts")
        ok &= check_snapshots(session)
    finally:
        session.close()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
