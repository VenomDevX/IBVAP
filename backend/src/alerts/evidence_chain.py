"""
IBVAP — Evidence chain verification and chain-safe retention.

The events and alerts tables carry an HMAC hash chain (see `evidence.py`).
Retention used to delete rows by timestamp, which broke verification: the first
surviving row is hashed against a predecessor that no longer exists. Purges now
remove only a *prefix* of each chained table and record a signed checkpoint with
the hash they cut at; the verifier accepts a missing head only at such a
checkpoint, so deleting rows outside a purge is still detected.
"""

from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import func

from src.alerts import evidence
from src.database.models import (
    AlertModel,
    EventEvidenceModel,
    EventModel,
    EvidenceCheckpointModel,
    IncidentNoteModel,
    OperatorFeedbackModel,
)

# Must match the field lists passed to Repository._chain().
EVENT_FIELDS = [
    "event_id", "camera_id", "track_id", "event_type", "timestamp",
    "object_type", "risk_score", "risk_level", "evidence_hash",
]
ALERT_FIELDS = [
    "alert_id", "camera_id", "event_id", "track_id", "event_type",
    "timestamp", "risk_score", "risk_level", "object_type", "snapshot_hash",
]

CHAINED = {
    "events": (EventModel, EVENT_FIELDS),
    "alerts": (AlertModel, ALERT_FIELDS),
}


@dataclass
class ChainReport:
    table: str
    rows: int = 0
    breaks: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.breaks


def _checkpoint_record(cp: EvidenceCheckpointModel) -> dict:
    return {
        "table_name": cp.table_name,
        "anchor_hash": cp.anchor_hash,
        "rows_purged": cp.rows_purged,
        "created_at": cp.created_at,
    }


def _valid_anchors(session, table: str) -> set[str]:
    anchors = set()
    for cp in session.query(EvidenceCheckpointModel).filter_by(table_name=table).all():
        if evidence.verify(_checkpoint_record(cp), None, cp.mac):
            anchors.add(cp.anchor_hash)
    return anchors


def verify_table(session, table: str) -> ChainReport:
    model, fields = CHAINED[table]
    report = ChainReport(table)
    rows = session.query(model).filter(model.chain_hash.isnot(None)).order_by(model.id).all()
    report.rows = len(rows)
    if not rows:
        return report

    head = rows[0]
    if head.prev_hash in (None, evidence.GENESIS) or head.prev_hash in _valid_anchors(session, table):
        prev = head.prev_hash
    else:
        # Rows were removed from the start of the chain without a purge checkpoint.
        report.breaks.append(f"{getattr(head, fields[0])} (chain head truncated)")
        prev = head.prev_hash

    for row in rows:
        record = {f: getattr(row, f) for f in fields}
        if not evidence.verify(record, prev, row.chain_hash):
            report.breaks.append(str(getattr(row, fields[0])))
        prev = row.chain_hash
    return report


def _prefix_boundary(session, model, cutoff: datetime, extra_keep_ids=()) -> int:
    """Smallest id that must survive: the first non-expired row, or a row we must keep."""
    first_live = session.query(func.min(model.id)).filter(model.timestamp >= cutoff).scalar()
    candidates = [i for i in (first_live, *extra_keep_ids) if i is not None]
    if candidates:
        return min(candidates)
    return (session.query(func.max(model.id)).scalar() or 0) + 1


def purge_chained_prefix(session, table: str, cutoff: datetime, dry_run: bool = False) -> int:
    """Delete the expired prefix of a chained table and checkpoint the cut."""
    model, _fields = CHAINED[table]
    extra = ()
    if table == "events":
        # Never delete an event a surviving alert still points at.
        extra = (
            session.query(func.min(EventModel.id))
            .join(AlertModel, AlertModel.event_id == EventModel.event_id)
            .scalar(),
        )
    boundary = _prefix_boundary(session, model, cutoff, extra)
    doomed = session.query(model).filter(model.id < boundary)
    count = doomed.count()
    if not count or dry_run:
        return count

    last_chained = (
        session.query(model.chain_hash)
        .filter(model.id < boundary, model.chain_hash.isnot(None))
        .order_by(model.id.desc())
        .first()
    )

    if table == "alerts":
        ids = session.query(AlertModel.alert_id).filter(AlertModel.id < boundary)
        session.query(IncidentNoteModel).filter(IncidentNoteModel.alert_id.in_(ids)).delete(synchronize_session=False)
        session.query(OperatorFeedbackModel).filter(OperatorFeedbackModel.alert_id.in_(ids)).delete(
            synchronize_session=False
        )
    else:
        ids = session.query(EventModel.event_id).filter(EventModel.id < boundary)
        session.query(EventEvidenceModel).filter(EventEvidenceModel.event_id.in_(ids)).delete(
            synchronize_session=False
        )
        session.query(OperatorFeedbackModel).filter(OperatorFeedbackModel.event_id.in_(ids)).delete(
            synchronize_session=False
        )
    doomed.delete(synchronize_session=False)

    if last_chained is not None:
        cp = EvidenceCheckpointModel(
            table_name=table,
            anchor_hash=last_chained[0],
            rows_purged=count,
            created_at=datetime.utcnow().replace(microsecond=0),
        )
        cp.mac = evidence.compute_hash(_checkpoint_record(cp), None)
        session.add(cp)
    session.commit()
    return count
