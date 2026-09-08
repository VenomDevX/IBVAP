"""
IBVAP — Database Models
SQLAlchemy ORM models matching TRD Section 17 schema.
"""

from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, Text, DateTime, ForeignKey, JSON
)
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
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    events = relationship("EventModel", back_populates="camera")
    alerts = relationship("AlertModel", back_populates="camera")


class TrackModel(Base):
    """Tracked object records."""
    __tablename__ = "tracks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    track_id = Column(Integer, nullable=False, index=True)
    camera_id = Column(String(50), ForeignKey("cameras.camera_id"), nullable=False)
    object_type = Column(String(50), nullable=False)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=True)
    trajectory = Column(JSON, default=list)  # List of [x, y, timestamp]
    total_distance = Column(Float, default=0.0)
    average_speed = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)


class EventModel(Base):
    """Security events (fused events from the context fusion engine)."""
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(String(50), unique=True, nullable=False, index=True)
    camera_id = Column(String(50), ForeignKey("cameras.camera_id"), nullable=False, index=True)
    track_id = Column(Integer, nullable=True)
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
    evidence_path = Column(String(500), nullable=True)
    evidence_hash = Column(String(64), nullable=True)
    prev_hash = Column(String(64), nullable=True)
    chain_hash = Column(String(64), nullable=True, index=True)
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
    event_id = Column(String(50), ForeignKey("events.event_id"), nullable=False)
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
    prev_hash = Column(String(64), nullable=True)
    chain_hash = Column(String(64), nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    camera = relationship("CameraModel", back_populates="alerts")
    event = relationship("EventModel", back_populates="alerts")


class IdentityResultModel(Base):
    """Face recognition identity results."""
    __tablename__ = "identity_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    identity_id = Column(String(50), unique=True, nullable=False)
    track_id = Column(Integer, nullable=False)
    camera_id = Column(String(50), nullable=False)
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
    camera_id = Column(String(50), nullable=False)
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
    camera_id = Column(String(50), nullable=False)
    name = Column(String(200), nullable=False)
    zone_type = Column(String(50), default="restricted")
    points = Column(JSON, default=list)
    color = Column(JSON, default=[255, 0, 0])
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
