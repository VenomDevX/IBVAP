"""
IBVAP — Database Models
SQLAlchemy ORM models matching TRD Section 17 schema.
"""

from datetime import datetime

from sqlalchemy import JSON, Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class CameraModel(Base):
    """Camera configuration and status."""

    __tablename__ = "cameras"

    id = Column(Integer, primary_key=True, autoincrement=True)
    camera_id = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(200), nullable=False)
    location_label = Column(String(200), default="")
    stream_url = Column(String(500), nullable=False)
    camera_type = Column(String(50), default="general")
    status = Column(String(20), default="offline")
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    enabled = Column(Boolean, default=True)
    fps_limit = Column(Integer, default=15)
    resolution = Column(JSON, nullable=True)
    # API field names a user changed (e.g. ["enabled"]). Startup's cameras.yaml
    # sync never overwrites these, so a user's choice survives a restart.
    user_overrides = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_heartbeat = Column(DateTime, nullable=True)
    last_frame_at = Column(DateTime, nullable=True)
    stream_status = Column(String(20), default="offline")

    # Relationships
    events = relationship("EventModel", back_populates="camera")
    alerts = relationship("AlertModel", back_populates="camera")


class TrackModel(Base):
    """Tracked object records."""

    __tablename__ = "tracks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    track_id = Column(Integer, nullable=False, index=True)
    track_uuid = Column(String(64), unique=True, nullable=False, index=True)
    session_id = Column(String(64), nullable=False, index=True)
    camera_id = Column(String(50), ForeignKey("cameras.camera_id"), nullable=False, index=True)
    object_type = Column(String(50), nullable=False)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=True)
    last_seen = Column(DateTime, nullable=False, index=True)
    status = Column(String(20), default="NEW", nullable=False, index=True)
    trajectory = Column(JSON, default=list)  # List of [x, y, timestamp]
    total_distance = Column(Float, default=0.0)
    average_speed = Column(Float, default=0.0)
    best_snapshot = Column(String(500), nullable=True)
    best_confidence = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)


class EventModel(Base):
    """Security events (fused events from the context fusion engine)."""

    __tablename__ = "events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(String(50), unique=True, nullable=False, index=True)
    camera_id = Column(String(50), ForeignKey("cameras.camera_id"), nullable=False, index=True)
    track_id = Column(Integer, nullable=True)
    track_uuid = Column(String(64), nullable=True, index=True)
    zone_id = Column(String(50), nullable=True, index=True)
    event_type = Column(String(100), nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    duration = Column(Float, default=0.0)
    object_type = Column(String(50), default="")
    confidence = Column(Float, default=0.0)
    risk_score = Column(Float, default=0.0)
    risk_level = Column(String(20), default="low", index=True)
    contributing_factors = Column(JSON, default=list)
    spatial_context = Column(JSON, default=dict)
    temporal_context = Column(JSON, default=dict)
    state = Column(String(20), default="OPEN", nullable=False, index=True)
    opened_at = Column(DateTime, nullable=True, index=True)
    last_updated = Column(DateTime, nullable=True, index=True)
    closed_at = Column(DateTime, nullable=True)
    # The risk assessment as first recorded. Escalation rewrites risk_score /
    # risk_level in place, so these immutable copies are what the hash chain
    # commits to.
    original_risk_score = Column(Float, nullable=True)
    original_risk_level = Column(String(20), nullable=True)
    score_breakdown = Column(JSON, default=dict)
    dedupe_key = Column(String(500), nullable=True, index=True)
    evidence_path = Column(String(500), nullable=True)
    evidence_hash = Column(String(64), nullable=True)
    prev_hash = Column(String(64), nullable=True)
    chain_hash = Column(String(64), nullable=True, index=True)
    # NULL = v1 (hashed risk_score/risk_level, which escalation later changes);
    # 2 = only fields that never change after insert (left the risk assessment
    # uncovered); 3 = adds original_risk_*. See alerts/evidence_chain.py.
    chain_version = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    camera = relationship("CameraModel", back_populates="events")
    alerts = relationship("AlertModel", back_populates="event")


class AlertModel(Base):
    """Alert records."""

    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    alert_id = Column(String(50), unique=True, nullable=False, index=True)
    camera_id = Column(String(50), ForeignKey("cameras.camera_id"), nullable=False, index=True)
    event_id = Column(String(50), ForeignKey("events.event_id"), nullable=False, index=True)
    track_id = Column(Integer, nullable=True)
    event_type = Column(String(100), nullable=False)
    timestamp = Column(DateTime, nullable=False, index=True)
    risk_score = Column(Float, default=0.0)
    risk_level = Column(String(20), default="low", index=True)
    object_type = Column(String(50), default="")
    contributing_factors = Column(JSON, default=list)
    snapshot_path = Column(String(500), nullable=True)
    snapshot_hash = Column(String(64), nullable=True)
    plate_result = Column(String(50), nullable=True)
    identity_result = Column(String(100), nullable=True)
    reviewed = Column(Boolean, default=False, index=True)
    reviewed_by = Column(String(100), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    status = Column(String(30), default="open", nullable=False, index=True)
    disposition = Column(String(30), nullable=True, index=True)
    assignee = Column(String(100), nullable=True, index=True)
    acknowledged_at = Column(DateTime, nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    acknowledged_by = Column(String(100), nullable=True)
    resolved_by = Column(String(100), nullable=True)
    # The risk assessment as first recorded. Escalation rewrites risk_score /
    # risk_level in place, so these immutable copies are what the hash chain
    # commits to.
    original_risk_score = Column(Float, nullable=True)
    original_risk_level = Column(String(20), nullable=True)
    false_positive = Column(Boolean, default=False, nullable=False)
    prev_hash = Column(String(64), nullable=True)
    chain_hash = Column(String(64), nullable=True, index=True)
    # NULL = v1 (hashed risk_score/risk_level, which escalation later changes);
    # 2 = only fields that never change after insert (left the risk assessment
    # uncovered); 3 = adds original_risk_*. See alerts/evidence_chain.py.
    chain_version = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    camera = relationship("CameraModel", back_populates="alerts")
    event = relationship("EventModel", back_populates="alerts")
    notes = relationship("IncidentNoteModel", back_populates="alert", order_by="IncidentNoteModel.created_at")


class IncidentNoteModel(Base):
    """Append-only operator notes attached to an alert/incident."""

    __tablename__ = "incident_notes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    alert_id = Column(String(50), ForeignKey("alerts.alert_id"), nullable=False, index=True)
    author = Column(String(100), nullable=False)
    note = Column(String(4000), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    alert = relationship("AlertModel", back_populates="notes")


class IdentityResultModel(Base):
    """Face recognition identity results."""

    __tablename__ = "identity_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    identity_id = Column(String(50), unique=True, nullable=False)
    track_id = Column(Integer, nullable=False)
    camera_id = Column(String(50), ForeignKey("cameras.camera_id"), nullable=False, index=True)
    identity_label = Column(String(200), default="unknown")
    similarity_score = Column(Float, default=0.0)
    timestamp = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class ANPRResultModel(Base):
    """License plate recognition results."""

    __tablename__ = "anpr_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    plate_id = Column(String(50), unique=True, nullable=False)
    track_id = Column(Integer, nullable=False)
    camera_id = Column(String(50), ForeignKey("cameras.camera_id"), nullable=False, index=True)
    plate_text = Column(String(20), default="")
    ocr_confidence = Column(Float, default=0.0)
    timestamp = Column(DateTime, nullable=False)
    plate_image_path = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class UserModel(Base):
    """System users for authentication."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(100), unique=True, nullable=False)
    hashed_password = Column(String(200), nullable=False)
    role = Column(String(50), default="operator")  # admin, operator, auditor
    full_name = Column(String(200), default="")
    is_active = Column(Boolean, default=True)
    allowed_areas = Column(JSON, default=list)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime, nullable=True)


class AuditLogModel(Base):
    """Audit log for important actions."""

    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    action = Column(String(100), nullable=False)
    username = Column(String(100), nullable=False, index=True)
    details = Column(JSON, default=dict)
    ip_address = Column(String(50), nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)


class ZoneModel(Base):
    """Persistent zone configurations."""

    __tablename__ = "zones"

    id = Column(Integer, primary_key=True, autoincrement=True)
    zone_id = Column(String(50), unique=True, nullable=False)
    camera_id = Column(String(50), ForeignKey("cameras.camera_id"), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    zone_type = Column(String(50), default="restricted")
    points = Column(JSON, default=list)
    color = Column(JSON, default=[255, 0, 0])
    # Object classes that trigger this zone; NULL/empty = every class.
    trigger_classes = Column(JSON, nullable=True)
    enabled = Column(Boolean, default=True)
    deleted = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class RevokedTokenModel(Base):
    """Denylist of access tokens invalidated by an explicit logout."""

    __tablename__ = "revoked_tokens"

    id = Column(Integer, primary_key=True, autoincrement=True)
    token_hash = Column(String(64), unique=True, nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False, index=True)
    revoked_at = Column(DateTime, default=datetime.utcnow)


class CameraSessionModel(Base):
    """A stream connection epoch; tracker IDs are unique only inside it."""

    __tablename__ = "camera_sessions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(64), unique=True, nullable=False, index=True)
    camera_id = Column(String(50), ForeignKey("cameras.camera_id"), nullable=False, index=True)
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    ended_at = Column(DateTime, nullable=True)
    status = Column(String(20), default="ACTIVE", nullable=False, index=True)


class VehicleProfileModel(Base):
    """One deterministic dossier per persistent vehicle track."""

    __tablename__ = "vehicle_profiles"
    id = Column(Integer, primary_key=True, autoincrement=True)
    track_uuid = Column(String(64), unique=True, nullable=False, index=True)
    camera_id = Column(String(50), ForeignKey("cameras.camera_id"), nullable=False, index=True)
    vehicle_class = Column(String(50), nullable=False)
    first_seen = Column(DateTime, nullable=False)
    last_seen = Column(DateTime, nullable=False, index=True)
    track_duration = Column(Float, default=0.0)
    zone_history = Column(JSON, default=list)
    direction = Column(String(50), default="unknown")
    best_confidence = Column(Float, default=0.0)
    best_snapshot = Column(String(500), nullable=True)
    color = Column(String(30), default="Unknown")
    plate = Column(String(20), default="UNKNOWN", index=True)
    plate_confidence = Column(Float, default=0.0)
    watchlist_status = Column(String(30), default="UNKNOWN")
    threat_score = Column(Float, default=0.0)
    description = Column(String(1000), default="")


class OperatorFeedbackModel(Base):
    """Structured, append-only false-positive/quality feedback."""

    __tablename__ = "operator_feedback"
    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(String(50), ForeignKey("events.event_id"), nullable=False, index=True)
    alert_id = Column(String(50), ForeignKey("alerts.alert_id"), nullable=False, index=True)
    operator = Column(String(100), nullable=False, index=True)
    reason = Column(String(100), nullable=False)
    camera_id = Column(String(50), nullable=False, index=True)
    event_type = Column(String(100), nullable=False)
    model_confidence = Column(Float, default=0.0)
    track_information = Column(JSON, default=dict)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)


class EventEvidenceModel(Base):
    __tablename__ = "event_evidence"
    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(String(50), ForeignKey("events.event_id"), nullable=False, index=True)
    snapshot_path = Column(String(500), nullable=True)
    clip_path = Column(String(500), nullable=True)
    evidence_type = Column(String(30), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)


class EvidenceCheckpointModel(Base):
    """Where a retention purge cut a hash-chained table.

    `anchor_hash` is the chain hash of the last purged row, i.e. the prev_hash
    the first surviving row must carry. The verifier accepts a truncated chain
    head only at a recorded (and itself HMAC-signed) checkpoint.
    """

    __tablename__ = "evidence_checkpoints"
    id = Column(Integer, primary_key=True, autoincrement=True)
    table_name = Column(String(50), nullable=False, index=True)
    anchor_hash = Column(String(64), nullable=False)
    rows_purged = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    mac = Column(String(64), nullable=False)


class EvidenceChainHeadModel(Base):
    """Latest chain hash per chained table.

    Every append updates this row first, inside the same transaction, which
    takes the database write lock (SQLite) / a row lock (Postgres). That
    serialises chain appends across processes, so two backends sharing one
    database can no longer fork the chain.
    """

    __tablename__ = "evidence_chain_heads"
    table_name = Column(String(50), primary_key=True)
    head_hash = Column(String(64), nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class WatchlistEntryModel(Base):
    """A face or number plate operators want flagged.

    list_type: "wanted" (critical alert), "authorized" (known, lowers risk) or
    "vip" (informational). Face embeddings are stored Fernet-encrypted.
    """

    __tablename__ = "watchlist_entries"
    id = Column(Integer, primary_key=True, autoincrement=True)
    entry_id = Column(String(50), unique=True, nullable=False, index=True)
    kind = Column(String(10), nullable=False, index=True)  # face | plate
    list_type = Column(String(20), nullable=False, index=True)
    label = Column(String(200), nullable=False)
    plate = Column(String(20), nullable=True, index=True)  # normalised; plates only
    embedding_enc = Column(Text, nullable=True)  # faces only
    notes = Column(String(1000), default="")
    active = Column(Boolean, default=True, nullable=False, index=True)
    created_by = Column(String(100), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    deactivated_by = Column(String(100), nullable=True)
    deactivated_at = Column(DateTime, nullable=True)
