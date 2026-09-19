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
    EvidenceChainHeadModel,
    EvidenceCheckpointModel,
    IncidentNoteModel,
    OperatorFeedbackModel,
)

CURRENT_VERSION = 3

# Hashed fields per chain version.
# v1 hashed risk_score/risk_level, which incident escalation rewrites, so
#    escalated v1 rows can no longer verify.
# v2 dropped them, which left the risk assessment — the part of a record that
#    decides how an incident is triaged — covered by nothing.
# v3 hashes immutable copies taken at insert (original_risk_*) instead, so the
#    assessment is tamper-evident again while escalation stays free to rewrite
#    the mutable risk_score / risk_level.
EVENT_FIELDS = {
    1: ["event_id", "camera_id", "track_id", "event_type", "timestamp",
        "object_type", "risk_score", "risk_level", "evidence_hash"],
    2: ["event_id", "camera_id", "track_id", "event_type", "timestamp",
        "object_type", "evidence_hash"],
    3: ["event_id", "camera_id", "track_id", "event_type", "timestamp",
        "object_type", "original_risk_score", "original_risk_level", "evidence_hash"],
}
ALERT_FIELDS = {
    1: ["alert_id", "camera_id", "event_id", "track_id", "event_type",
        "timestamp", "risk_score", "risk_level", "object_type", "snapshot_hash"],
    2: ["alert_id", "camera_id", "event_id", "track_id", "event_type",
        "timestamp", "object_type", "snapshot_hash"],
    3: ["alert_id", "camera_id", "event_id", "track_id", "event_type",
        "timestamp", "original_risk_score", "original_risk_level",
        "object_type", "snapshot_hash"],
}

CHAINED = {
    "events": (EventModel, EVENT_FIELDS),
    "alerts": (AlertModel, ALERT_FIELDS),
}


def fields_for(table: str, version: int | None) -> list[str]:
    return CHAINED[table][1][version or 1]


def append(session, row, table: str) -> None:
    """Link `row` to the chain head. Call inside the transaction that inserts it."""
    model = CHAINED[table][0]
    head = (
        session.query(EvidenceChainHeadModel)
        .filter_by(table_name=table)
        .with_for_update()
        .one_or_none()
    )
    if head is None:
        head = EvidenceChainHeadModel(table_name=table)
        session.add(head)
    # Writing the head row first takes the write lock before the tail is read,
    # so a concurrent appender in another process waits instead of forking.
    head.updated_at = datetime.utcnow()
    session.flush()

    # Link to the newest row actually in the table (read under the lock). The
    # head row is only the lock + tail marker: a process still running older
    # code appends without updating it.
    last = session.query(model.chain_hash).filter(model.chain_hash.isnot(None)).order_by(model.id.desc()).first()
    prev = last[0] if last else None
    # Freeze the assessment as inserted; escalation may later change risk_score
    # / risk_level, but these copies are what the chain commits to.
    if row.original_risk_score is None:
        row.original_risk_score = row.risk_score
    if row.original_risk_level is None:
        row.original_risk_level = row.risk_level
    record = {f: getattr(row, f) for f in fields_for(table, CURRENT_VERSION)}
    row.chain_version = CURRENT_VERSION
    row.prev_hash = prev or evidence.GENESIS
    row.chain_hash = evidence.compute_hash(record, prev)
    head.head_hash = row.chain_hash


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
    model, _fields = CHAINED[table]
    report = ChainReport(table)
    # Read the head BEFORE the rows: a live backend may append meanwhile, and the
    # head we saw must then be somewhere in the rows we read.
    stored_head = session.query(EvidenceChainHeadModel.head_hash).filter_by(table_name=table).scalar()
    # Stream just the hashed columns: ORM objects for a few hundred thousand rows
    # cost gigabytes, and this runs next to a live, memory-hungry backend.
    all_fields = sorted({f for fields in CHAINED[table][1].values() for f in fields})
    columns = [getattr(model, f) for f in all_fields] + [model.prev_hash, model.chain_hash, model.chain_version]
    rows = (
        session.query(*columns)
        .filter(model.chain_hash.isnot(None))
        .order_by(model.id)
        .yield_per(5000)
    )

    prev = None
    seen = set()
    for index, row in enumerate(rows):
        fields = fields_for(table, row.chain_version)
        if index == 0:
            if row.prev_hash in (None, evidence.GENESIS) or row.prev_hash in _valid_anchors(session, table):
                prev = row.prev_hash
            else:
                # Rows were removed from the start of the chain without a purge checkpoint.
                report.breaks.append(f"{getattr(row, fields[0])} (chain head truncated)")
                prev = row.prev_hash
        record = {f: getattr(row, f) for f in fields}
        if not evidence.verify(record, prev, row.chain_hash):
            report.breaks.append(str(getattr(row, fields[0])))
        prev = row.chain_hash
        seen.add(row.chain_hash)
        report.rows += 1

    if stored_head and stored_head not in seen:
        # The newest row the chain recorded is gone: rows were removed from the end.
        report.breaks.append("(chain tail truncated: recorded head row is missing)")
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
