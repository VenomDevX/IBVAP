"""
IBVAP — Database Repository
CRUD operations for all entities.
"""

from datetime import datetime

from sqlalchemy import desc, or_
from sqlalchemy.orm import Session

from src.alerts import evidence
from src.database.models import (
    AlertModel,
    ANPRResultModel,
    AuditLogModel,
    CameraModel,
    EventModel,
    IdentityResultModel,
    UserModel,
    ZoneModel,
)


class Repository:
    """Database CRUD operations for all IBVAP entities."""

    def __init__(self, session: Session):
        self.session = session

    # ======================== CAMERAS ========================

    def create_camera(
        self,
        camera_id: str,
        name: str,
        stream_url: str,
        camera_type: str = "general",
        location_label: str = "",
        latitude: float = None,
        longitude: float = None,
    ) -> CameraModel:
        """Create a new camera configuration."""
        cam = CameraModel(
            camera_id=camera_id,
            name=name,
            stream_url=stream_url,
            camera_type=camera_type,
            location_label=location_label,
            latitude=latitude,
            longitude=longitude,
            status="offline",
            enabled=True,
        )
        self.session.add(cam)
        self.session.commit()
        return cam

    def get_camera(self, camera_id: str) -> CameraModel | None:
        return self.session.query(CameraModel).filter_by(camera_id=camera_id).first()

    def get_all_cameras(self) -> list[CameraModel]:
        return self.session.query(CameraModel).all()

    def update_camera_status(self, camera_id: str, status: str):
        camera = self.get_camera(camera_id)
        if camera:
            camera.status = status
            camera.updated_at = datetime.utcnow()
            self.session.commit()

    # ======================== EVENTS ========================

    def create_event(self, event_data: dict, commit: bool = True) -> EventModel:
        existing = self.get_event(event_data["event_id"])
        if existing is not None:
            if existing.camera_id != event_data["camera_id"] or existing.track_id != event_data.get("track_id"):
                raise ValueError("Event ID already belongs to another track")
            return existing  # fusion re-emits the same event_id for an ongoing situation
        event = EventModel(
            event_id=event_data["event_id"],
            camera_id=event_data["camera_id"],
            track_id=event_data.get("track_id"),
            event_type=event_data["event_type"],
            timestamp=datetime.fromtimestamp(event_data["timestamp"]),
            duration=event_data.get("duration", 0.0),
            object_type=event_data.get("object_type", ""),
            risk_score=event_data.get("risk_score", 0.0),
            risk_level=event_data.get("risk_level", "low"),
            contributing_factors=event_data.get("contributing_factors", []),
            spatial_context=event_data.get("spatial_context", {}),
            temporal_context=event_data.get("temporal_context", {}),
            evidence_path=event_data.get("evidence_path"),
            evidence_hash=event_data.get("evidence_hash"),
        )
        self._chain(
            event,
            EventModel,
            [
                "event_id",
                "camera_id",
                "track_id",
                "event_type",
                "timestamp",
                "object_type",
                "risk_score",
                "risk_level",
                "evidence_hash",
            ],
        )
        self.session.add(event)
        self.session.flush()
        if commit:
            self.session.commit()
        return event

    def _chain(self, row, model, fields):
        """Attach prev_hash / chain_hash linking this row to the previous one."""
        last = (
            self.session.query(model.chain_hash).filter(model.chain_hash.isnot(None)).order_by(desc(model.id)).first()
        )
        prev = last[0] if last else None
        record = {f: getattr(row, f) for f in fields}
        row.prev_hash = prev or evidence.GENESIS
        row.chain_hash = evidence.compute_hash(record, prev)

    def get_event(self, event_id: str) -> EventModel | None:
        return self.session.query(EventModel).filter_by(event_id=event_id).first()

    def delete_before(self, model, cutoff, ts_field="timestamp") -> int:
        """Delete rows older than `cutoff` (a datetime). Returns the count."""
        col = getattr(model, ts_field)
        q = self.session.query(model).filter(col < cutoff)
        n = q.count()
        q.delete(synchronize_session=False)
        self.session.commit()
        return n

    def get_events(
        self,
        camera_id: str = None,
        event_type: str = None,
        risk_level: str = None,
        limit: int = 100,
        offset: int = 0,
        allowed_cameras=None,
    ) -> list[EventModel]:
        query = self.session.query(EventModel)
        if allowed_cameras is not None:
            query = query.filter(EventModel.camera_id.in_(allowed_cameras or ["__none__"]))
        if camera_id:
            query = query.filter_by(camera_id=camera_id)
        if event_type:
            query = query.filter_by(event_type=event_type)
        if risk_level:
            query = query.filter_by(risk_level=risk_level)
        return query.order_by(desc(EventModel.timestamp)).offset(offset).limit(limit).all()

    def get_event_count(self, camera_id: str = None, allowed_cameras=None) -> int:
        query = self.session.query(EventModel)
        if allowed_cameras is not None:
            query = query.filter(EventModel.camera_id.in_(allowed_cameras or ["__none__"]))
        if camera_id:
            query = query.filter_by(camera_id=camera_id)
        return query.count()

    # ======================== ALERTS ========================

    def create_alert(self, alert_data: dict, commit: bool = True) -> AlertModel:
        alert = AlertModel(
            alert_id=alert_data["alert_id"],
            camera_id=alert_data["camera_id"],
            event_id=alert_data["event_id"],
            track_id=alert_data.get("track_id"),
            event_type=alert_data["event_type"],
            timestamp=datetime.fromtimestamp(alert_data["timestamp"]),
            risk_score=alert_data.get("risk_score", 0.0),
            risk_level=alert_data.get("risk_level", "low"),
            object_type=alert_data.get("object_type", ""),
            contributing_factors=alert_data.get("contributing_factors", []),
            snapshot_path=alert_data.get("snapshot_path"),
            snapshot_hash=alert_data.get("snapshot_hash"),
            plate_result=alert_data.get("plate_result"),
            identity_result=alert_data.get("identity_result"),
        )
        self._chain(
            alert,
            AlertModel,
            [
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
            ],
        )
        self.session.add(alert)
        self.session.flush()
        if commit:
            self.session.commit()
        return alert

    def get_alert(self, alert_id: str) -> AlertModel | None:
        return self.session.query(AlertModel).filter_by(alert_id=alert_id).first()

    def get_alerts(
        self,
        camera_id: str = None,
        risk_level: str = None,
        reviewed: bool = None,
        limit: int = 100,
        allowed_cameras=None,
    ) -> list[AlertModel]:
        query = self.session.query(AlertModel)
        if allowed_cameras is not None:
            query = query.filter(AlertModel.camera_id.in_(allowed_cameras or ["__none__"]))
        if camera_id:
            query = query.filter_by(camera_id=camera_id)
        if risk_level:
            query = query.filter_by(risk_level=risk_level)
        if reviewed is not None:
            query = query.filter_by(reviewed=reviewed)
        return query.order_by(desc(AlertModel.timestamp)).limit(limit).all()

    def mark_alert_reviewed(self, alert_id: str, reviewed_by: str = "operator") -> bool:
        alert = self.get_alert(alert_id)
        if alert:
            alert.reviewed = True
            alert.reviewed_by = reviewed_by
            alert.reviewed_at = datetime.utcnow()
            self.session.commit()
            return True
        return False

    # ======================== USERS ========================

    def create_user(
        self,
        username: str,
        hashed_password: str,
        role: str = "operator",
        full_name: str = "",
        allowed_areas: list = None,
        is_active: bool = True,
    ) -> UserModel:
        user = UserModel(
            username=username,
            hashed_password=hashed_password,
            role=role,
            full_name=full_name,
            allowed_areas=allowed_areas or [],
            is_active=is_active,
        )
        self.session.add(user)
        self.session.commit()
        return user

    def get_user(self, username: str) -> UserModel | None:
        return self.session.query(UserModel).filter_by(username=username).first()

    def get_all_users(self) -> list[UserModel]:
        return self.session.query(UserModel).all()

    def count_users(self) -> int:
        return self.session.query(UserModel).count()

    # ======================== AUDIT LOGS ========================

    def create_audit_log(self, action: str, username: str, details: dict = None, ip_address: str = None):
        log = AuditLogModel(action=action, username=username, details=details or {}, ip_address=ip_address)
        self.session.add(log)
        self.session.commit()

    def get_audit_logs(self, limit: int = 100) -> list[AuditLogModel]:
        return self.session.query(AuditLogModel).order_by(desc(AuditLogModel.timestamp)).limit(limit).all()

    # ======================== IDENTITY / ANPR RESULTS ========================

    def create_identity_result(
        self, track_id: int, camera_id: str, identity_label: str, similarity_score: float
    ) -> IdentityResultModel:
        import uuid

        row = IdentityResultModel(
            identity_id=f"IDN_{uuid.uuid4().hex[:12]}",
            track_id=track_id,
            camera_id=camera_id,
            identity_label=identity_label,
            similarity_score=similarity_score,
            timestamp=datetime.utcnow(),
        )
        self.session.add(row)
        self.session.commit()
        return row

    def get_identity_results(self, camera_id: str = None, limit: int = 100) -> list[IdentityResultModel]:
        q = self.session.query(IdentityResultModel)
        if camera_id:
            q = q.filter_by(camera_id=camera_id)
        return q.order_by(desc(IdentityResultModel.timestamp)).limit(limit).all()

    def create_anpr_result(
        self,
        track_id: int,
        camera_id: str,
        plate_text: str,
        ocr_confidence: float,
        plate_image_path: str = None,
    ) -> ANPRResultModel:
        import uuid

        row = ANPRResultModel(
            plate_id=f"PLT_{uuid.uuid4().hex[:12]}",
            track_id=track_id,
            camera_id=camera_id,
            plate_text=plate_text,
            ocr_confidence=ocr_confidence,
            timestamp=datetime.utcnow(),
            plate_image_path=plate_image_path,
        )
        self.session.add(row)
        self.session.commit()
        return row

    def get_anpr_results(self, camera_id: str = None, limit: int = 100) -> list[ANPRResultModel]:
        q = self.session.query(ANPRResultModel)
        if camera_id:
            q = q.filter_by(camera_id=camera_id)
        return q.order_by(desc(ANPRResultModel.timestamp)).limit(limit).all()

    # ======================== ZONES ========================

    def create_zone(self, zone_data: dict) -> ZoneModel:
        zone = ZoneModel(
            zone_id=zone_data["zone_id"],
            camera_id=zone_data["camera_id"],
            name=zone_data["name"],
            zone_type=zone_data.get("type", "restricted"),
            points=zone_data.get("points", []),
            color=zone_data.get("color", [255, 0, 0]),
            enabled=zone_data.get("enabled", True),
        )
        self.session.add(zone)
        self.session.commit()
        return zone

    def get_zones(self, camera_id: str = None, include_deleted: bool = False) -> list[ZoneModel]:
        query = self.session.query(ZoneModel)
        if not include_deleted:
            query = query.filter_by(deleted=False)
        if camera_id:
            query = query.filter_by(camera_id=camera_id)
        return query.all()

    def delete_zone(self, zone_id: str) -> bool:
        zone = self.session.query(ZoneModel).filter_by(zone_id=zone_id).first()
        if zone and not zone.deleted:
            zone.deleted = True
            zone.enabled = False
            self.session.commit()
            return True
        return False

    # ======================== STATISTICS ========================

    def get_dashboard_stats(self, allowed_cameras=None) -> dict:
        """Get statistics for the dashboard."""
        events = self.session.query(EventModel)
        alerts = self.session.query(AlertModel)
        camera_query = self.session.query(CameraModel)
        if allowed_cameras is not None:
            events = events.filter(EventModel.camera_id.in_(allowed_cameras))
            alerts = alerts.filter(AlertModel.camera_id.in_(allowed_cameras))
            camera_query = camera_query.filter(CameraModel.camera_id.in_(allowed_cameras))
        total_events = events.count()
        total_alerts = alerts.count()
        unreviewed = alerts.filter_by(reviewed=False).count()
        cameras = camera_query.count()

        # Risk level distribution
        from sqlalchemy import func

        risk_dist = dict(
            alerts.with_entities(AlertModel.risk_level, func.count(AlertModel.id)).group_by(AlertModel.risk_level).all()
        )

        # Event type distribution
        event_dist = dict(
            events.with_entities(EventModel.event_type, func.count(EventModel.id)).group_by(EventModel.event_type).all()
        )

        return {
            "total_events": total_events,
            "total_alerts": total_alerts,
            "unreviewed_alerts": unreviewed,
            "cameras": cameras,
            "risk_distribution": risk_dist,
            "event_distribution": event_dist,
        }

    def close(self):
        self.session.close()

    def get_snapshot_cameras(self, name: str) -> set[str]:
        owners = set()
        for model, field in ((EventModel, EventModel.evidence_path), (AlertModel, AlertModel.snapshot_path)):
            rows = self.session.query(model.camera_id).filter(or_(
                field == name, field.endswith("/" + name, autoescape=True),
                field.endswith("\\" + name, autoescape=True),
            )).all()
            owners.update(camera_id for (camera_id,) in rows)
        return owners
