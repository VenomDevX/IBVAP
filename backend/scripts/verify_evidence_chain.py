"""
verify_evidence_chain.py — check the alert/event tamper-evident hash chain.

Walks each table in insert order, recomputes the HMAC chain, and reports every
broken link. A chain head removed by purge_expired.py is accepted only at a
signed checkpoint. Also re-hashes each snapshot file and flags mismatches.

  # env: EVIDENCE_HMAC_KEY (same key used when the rows were written)
  python scripts/verify_evidence_chain.py
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.alerts import evidence
from src.alerts.evidence_chain import CHAINED, verify_table
from src.database.db import get_database
from src.database.models import AlertModel


def check(session, table):
    report = verify_table(session, table)
    status = "OK" if report.ok else f"BROKEN at {report.breaks}"
    print(f"[{table}] {report.rows} chained rows  ->  {status}")
    return report.ok


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
        ok = True
        for table in CHAINED:
            ok &= check(session, table)
        ok &= check_snapshots(session)
    finally:
        session.close()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
