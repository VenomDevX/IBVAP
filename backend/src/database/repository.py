"""
IBVAP — Database Repository
CRUD operations for all entities.
"""

from datetime import datetime

from sqlalchemy import asc, case, desc, or_
from sqlalchemy.orm import Session

from src.alerts import evidence_chain
from src.database.models import (
    AlertModel,
    ANPRResultModel,
    AuditLogModel,
    CameraModel,
    CameraSessionModel,
    EventEvidenceModel,
    EventModel,
    IdentityResultModel,
    IncidentNoteModel,
    OperatorFeedbackModel,
    TrackModel,
    UserModel,
    VehicleProfileModel,
    WatchlistEntryModel,
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
        enabled: bool = True,
        fps_limit: int = 15,
        resolution: list | None = None,
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
            enabled=enabled,
            fps_limit=fps_limit,
            resolution=resolution,
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

    def update_camera_runtime(self, camera_id: str, status: str, last_frame_at: float | None = None) -> None:
        camera = self.get_camera(camera_id)
        if camera is None:
            return
        camera.status = status
        camera.stream_status = status
        camera.last_heartbeat = datetime.utcnow()
        if last_frame_at is not None:
            camera.last_frame_at = datetime.utcfromtimestamp(last_frame_at)
        camera.updated_at = datetime.utcnow()
        self.session.commit()

    CAMERA_FIELDS = {
        "name": "name", "source": "stream_url", "type": "camera_type",
        "location": "location_label", "latitude": "latitude", "longitude": "longitude",
        "enabled": "enabled", "fps_limit": "fps_limit", "resolution": "resolution",
    }

    def update_camera(self, camera_id: str, changes: dict, by_user: bool = False) -> CameraModel | None:
        """by_user: the change came from a person (API), so remember those fields
        and never let the cameras.yaml startup sync overwrite them."""
        camera = self.get_camera(camera_id)
        if camera is None:
            return None
        touched = []
        for source, target in self.CAMERA_FIELDS.items():
            if source in changes:
                if getattr(camera, target) != changes[source]:
                    touched.append(source)
                setattr(camera, target, changes[source])
        if by_user and touched:
            # Only fields whose value changed: re-saving a form unchanged must not
            # freeze every field against future cameras.yaml updates.
            camera.user_overrides = sorted(set(camera.user_overrides or []) | set(touched))
        camera.updated_at = datetime.utcnow()
        self.session.commit()
        return camera

    def retire_camera(self, camera_id: str) -> CameraModel | None:
        camera = self.get_camera(camera_id)
        if camera is None:
            return None
        camera.enabled = False
        camera.status = "retired"
        camera.user_overrides = sorted(set(camera.user_overrides or []) | {"enabled"})
        camera.updated_at = datetime.utcnow()
        self.session.commit()
        return camera

    def start_camera_session(self, camera_id: str, session_id: str) -> CameraSessionModel:
        row = self.session.query(CameraSessionModel).filter_by(session_id=session_id).first()
        if row is None:
            row = CameraSessionModel(session_id=session_id, camera_id=camera_id, status="ACTIVE")
            self.session.add(row)
            self.session.commit()
        return row

    def close_camera_session(self, session_id: str) -> CameraSessionModel | None:
        row = self.session.query(CameraSessionModel).filter_by(session_id=session_id).first()
        if row is not None and row.status != "CLOSED":
            row.status = "CLOSED"
            row.ended_at = datetime.utcnow()
            self.session.commit()
        return row

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
            timestamp=datetime.utcfromtimestamp(event_data["timestamp"]),
            duration=event_data.get("duration", 0.0),
            object_type=event_data.get("object_type", ""),
            confidence=event_data.get("confidence", 0.0),
            risk_score=event_data.get("risk_score", 0.0),
            risk_level=event_data.get("risk_level", "low"),
            contributing_factors=event_data.get("contributing_factors", []),
            spatial_context=event_data.get("spatial_context", {}),
            temporal_context=event_data.get("temporal_context", {}),
            track_uuid=event_data.get("track_uuid") or None,
            zone_id=event_data.get("zone_id"),
            state=event_data.get("state", "OPEN"),
            opened_at=self._utc_from_epoch(event_data.get("opened_at")),
            last_updated=self._utc_from_epoch(event_data.get("last_updated")),
            closed_at=self._utc_from_epoch(event_data.get("closed_at")),
            score_breakdown=event_data.get("score_breakdown", {}),
            dedupe_key=event_data.get("dedupe_key") or None,
            evidence_path=event_data.get("evidence_path"),
            evidence_hash=event_data.get("evidence_hash"),
        )
        evidence_chain.append(self.session, event, "events")
        self.session.add(event)
        self.session.flush()
        if commit:
            self.session.commit()
        return event

    @staticmethod
    def _utc_from_epoch(value):
        return datetime.utcfromtimestamp(value) if value is not None else None

    def update_event_lifecycle(self, event_data: dict, commit: bool = True) -> EventModel | None:
        event = self.get_event(event_data["event_id"])
        if event is None:
            return None
        event.duration = event_data.get("duration", event.duration)
        event.confidence = event_data.get("confidence", event.confidence)
        event.risk_score = event_data.get("risk_score", event.risk_score)
        event.risk_level = event_data.get("risk_level", event.risk_level)
        event.contributing_factors = event_data.get("contributing_factors", event.contributing_factors)
        event.spatial_context = event_data.get("spatial_context", event.spatial_context)
        event.temporal_context = event_data.get("temporal_context", event.temporal_context)
        event.score_breakdown = event_data.get("score_breakdown", event.score_breakdown)
        event.state = event_data.get("state", event.state)
        event.last_updated = self._utc_from_epoch(event_data.get("last_updated")) or datetime.utcnow()
        event.closed_at = self._utc_from_epoch(event_data.get("closed_at"))
        if commit:
            self.session.commit()
        else:
            self.session.flush()
        return event

    def create_event_evidence(
        self, event_id: str, evidence_type: str, snapshot_path: str | None = None,
        clip_path: str | None = None, commit: bool = True,
    ) -> EventEvidenceModel:
        row = EventEvidenceModel(
            event_id=event_id, evidence_type=evidence_type,
            snapshot_path=snapshot_path, clip_path=clip_path,
        )
        self.session.add(row)
        if commit:
            self.session.commit()
        else:
            self.session.flush()
        return row

    def get_event_evidence(self, event_id: str) -> list[EventEvidenceModel]:
        return self.session.query(EventEvidenceModel).filter_by(event_id=event_id).order_by(EventEvidenceModel.created_at).all()

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
        start_time: datetime = None,
        end_time: datetime = None,
        search: str = None,
        sort_by: str = "timestamp",
        sort_order: str = "desc",
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
        if start_time:
            query = query.filter(EventModel.timestamp >= start_time)
        if end_time:
            query = query.filter(EventModel.timestamp <= end_time)
        if search:
            term = f"%{search}%"
            query = query.filter(or_(
                EventModel.event_id.ilike(term), EventModel.event_type.ilike(term),
                EventModel.camera_id.ilike(term), EventModel.object_type.ilike(term),
            ))
        sort_columns = {
            "timestamp": EventModel.timestamp,
            "risk_score": EventModel.risk_score,
            "camera_id": EventModel.camera_id,
            "event_type": EventModel.event_type,
        }
        column = sort_columns.get(sort_by, EventModel.timestamp)
        ordering = asc(column) if sort_order == "asc" else desc(column)
        return query.order_by(ordering).offset(offset).limit(limit).all()

    def get_event_count(
        self, camera_id: str = None, event_type: str = None, risk_level: str = None,
        start_time: datetime = None, end_time: datetime = None, search: str = None,
        allowed_cameras=None,
    ) -> int:
        query = self.session.query(EventModel)
        if allowed_cameras is not None:
            query = query.filter(EventModel.camera_id.in_(allowed_cameras or ["__none__"]))
        if camera_id:
            query = query.filter_by(camera_id=camera_id)
        if event_type:
            query = query.filter_by(event_type=event_type)
        if risk_level:
            query = query.filter_by(risk_level=risk_level)
        if start_time:
            query = query.filter(EventModel.timestamp >= start_time)
        if end_time:
            query = query.filter(EventModel.timestamp <= end_time)
        if search:
            term = f"%{search}%"
            query = query.filter(or_(
                EventModel.event_id.ilike(term), EventModel.event_type.ilike(term),
                EventModel.camera_id.ilike(term), EventModel.object_type.ilike(term),
            ))
        return query.count()

    # ======================== ALERTS ========================

    def create_alert(self, alert_data: dict, commit: bool = True) -> AlertModel:
        existing = self.session.query(AlertModel).filter_by(event_id=alert_data["event_id"]).first()
        if existing is not None:
            return existing
        alert = AlertModel(
            alert_id=alert_data["alert_id"],
            camera_id=alert_data["camera_id"],
            event_id=alert_data["event_id"],
            track_id=alert_data.get("track_id"),
            event_type=alert_data["event_type"],
            timestamp=datetime.utcfromtimestamp(alert_data["timestamp"]),
            risk_score=alert_data.get("risk_score", 0.0),
            risk_level=alert_data.get("risk_level", "low"),
            object_type=alert_data.get("object_type", ""),
            contributing_factors=alert_data.get("contributing_factors", []),
            snapshot_path=alert_data.get("snapshot_path"),
            snapshot_hash=alert_data.get("snapshot_hash"),
            plate_result=alert_data.get("plate_result"),
            identity_result=alert_data.get("identity_result"),
        )
        evidence_chain.append(self.session, alert, "alerts")
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
        offset: int = 0,
        status: str = None,
        active_only: bool = False,
        start_time: datetime = None,
        end_time: datetime = None,
        search: str = None,
        sort_by: str = "priority",
        sort_order: str = "desc",
        allowed_cameras=None,
    ) -> list[AlertModel]:
        query = self.session.query(AlertModel)
        if active_only:
            query = query.join(EventModel, AlertModel.event_id == EventModel.event_id).filter(
                EventModel.state.in_(("OPEN", "ACTIVE"))
            )
        if allowed_cameras is not None:
            query = query.filter(AlertModel.camera_id.in_(allowed_cameras or ["__none__"]))
        if camera_id:
            query = query.filter(AlertModel.camera_id == camera_id)
        if risk_level:
            query = query.filter(AlertModel.risk_level == risk_level)
        if reviewed is not None:
            query = query.filter(AlertModel.reviewed == reviewed)
        if status:
            query = query.filter(AlertModel.status == status)
        if start_time:
            query = query.filter(AlertModel.timestamp >= start_time)
        if end_time:
            query = query.filter(AlertModel.timestamp <= end_time)
        if search:
            term = f"%{search}%"
            query = query.filter(or_(
                AlertModel.alert_id.ilike(term), AlertModel.event_type.ilike(term),
                AlertModel.camera_id.ilike(term), AlertModel.object_type.ilike(term),
                AlertModel.assignee.ilike(term),
            ))
        sort_columns = {
            "timestamp": AlertModel.timestamp,
            "risk_score": AlertModel.risk_score,
            "status": AlertModel.status,
            "camera_id": AlertModel.camera_id,
        }
        if sort_by == "priority":
            status_rank = case(
                (AlertModel.status == "open", 0),
                (AlertModel.status == "reopened", 0),
                (AlertModel.status == "investigating", 1),
                (AlertModel.status == "acknowledged", 2),
                (AlertModel.status == "resolved", 3),
                (AlertModel.status == "false_positive", 4),
                else_=5,
            )
            severity_rank = case(
                (AlertModel.risk_level == "critical", 0),
                (AlertModel.risk_level == "high", 1),
                (AlertModel.risk_level == "medium", 2),
                (AlertModel.risk_level == "low", 3),
                else_=4,
            )
            return query.order_by(status_rank, severity_rank, desc(AlertModel.timestamp)).offset(offset).limit(limit).all()
        column = sort_columns.get(sort_by, AlertModel.timestamp)
        ordering = asc(column) if sort_order == "asc" else desc(column)
        return query.order_by(ordering, desc(AlertModel.timestamp)).offset(offset).limit(limit).all()

    def count_alerts(
        self,
        camera_id: str = None,
        risk_level: str = None,
        reviewed: bool = None,
        status: str = None,
        active_only: bool = False,
        start_time: datetime = None,
        end_time: datetime = None,
        search: str = None,
        allowed_cameras=None,
    ) -> int:
        query = self.session.query(AlertModel)
        if active_only:
            query = query.join(EventModel, AlertModel.event_id == EventModel.event_id).filter(
                EventModel.state.in_(("OPEN", "ACTIVE"))
            )
        if allowed_cameras is not None:
            query = query.filter(AlertModel.camera_id.in_(allowed_cameras or ["__none__"]))
        if camera_id:
            query = query.filter(AlertModel.camera_id == camera_id)
        if risk_level:
            query = query.filter(AlertModel.risk_level == risk_level)
        if reviewed is not None:
            query = query.filter(AlertModel.reviewed == reviewed)
        if status:
            query = query.filter(AlertModel.status == status)
        if start_time:
            query = query.filter(AlertModel.timestamp >= start_time)
        if end_time:
            query = query.filter(AlertModel.timestamp <= end_time)
        if search:
            term = f"%{search}%"
            query = query.filter(or_(
                AlertModel.alert_id.ilike(term), AlertModel.event_type.ilike(term),
                AlertModel.camera_id.ilike(term), AlertModel.object_type.ilike(term),
                AlertModel.assignee.ilike(term),
            ))
        return query.count()

    def mark_alert_reviewed(self, alert_id: str, reviewed_by: str = "operator") -> bool:
        alert = self.get_alert(alert_id)
        if alert:
            alert.reviewed = True
            alert.reviewed_by = reviewed_by
            alert.reviewed_at = datetime.utcnow()
            self.session.commit()
            return True
        return False

    def update_alert_workflow(
        self,
        alert_id: str,
        actor: str,
        status: str | None = None,
        disposition: str | None = None,
        assignee: str | None = None,
        note: str | None = None,
    ) -> AlertModel | None:
        alert = self.get_alert(alert_id)
        if alert is None:
            return None
        now = datetime.utcnow()
        if status is not None:
            alert.status = status
            if status in {"acknowledged", "investigating"} and alert.acknowledged_at is None:
                alert.acknowledged_at = now
                alert.acknowledged_by = actor
            if status in {"resolved", "false_positive"}:
                alert.resolved_at = now
                alert.resolved_by = actor
                alert.false_positive = status == "false_positive"
                alert.reviewed = True
                alert.reviewed_by = actor
                alert.reviewed_at = now
            elif status == "reopened":
                alert.resolved_at = None
                alert.resolved_by = None
                alert.false_positive = False
                alert.reviewed = False
        if disposition is not None:
            alert.disposition = disposition or None
        if assignee is not None:
            alert.assignee = assignee or None
        if note:
            self.session.add(IncidentNoteModel(alert_id=alert_id, author=actor, note=note))
        self.session.commit()
        return alert

    def update_alert_from_event(self, event_data: dict, commit: bool = True) -> AlertModel | None:
        alert = self.session.query(AlertModel).filter_by(event_id=event_data["event_id"]).first()
        if alert is None:
            return None
        alert.risk_score = event_data.get("risk_score", alert.risk_score)
        alert.risk_level = event_data.get("risk_level", alert.risk_level)
        alert.contributing_factors = event_data.get("contributing_factors", alert.contributing_factors)
        if commit:
            self.session.commit()
        else:
            self.session.flush()
        return alert

    @staticmethod
    def _new_track_row(track) -> TrackModel:
        return TrackModel(
            track_id=track.track_id, track_uuid=track.track_uuid, session_id=track.session_id,
            camera_id=track.camera_id, object_type=track.object_type,
            start_time=datetime.utcfromtimestamp(track.first_seen),
            last_seen=datetime.utcfromtimestamp(track.last_seen), status=track.status,
        )

    @staticmethod
    def _apply_track_fields(row: TrackModel, track) -> None:
        row.last_seen = datetime.utcfromtimestamp(track.last_seen)
        row.end_time = datetime.utcfromtimestamp(track.last_seen) if track.status == "CLOSED" else None
        row.status = track.status
        row.trajectory = [list(point) for point in track.trajectory]
        row.total_distance = track.total_distance
        row.average_speed = track.average_speed
        row.best_snapshot = track.best_snapshot_path
        row.best_confidence = track.confidence

    def upsert_track(self, track, commit: bool = True) -> TrackModel:
        row = self.session.query(TrackModel).filter_by(track_uuid=track.track_uuid).first()
        if row is None:
            row = self._new_track_row(track)
            self.session.add(row)
        self._apply_track_fields(row, track)
        if commit:
            self.session.commit()
        else:
            self.session.flush()
        return row

    def upsert_track_profiles(self, tracks, vehicle_types: set[str]) -> None:
        """Upsert many tracks (plus vehicle profiles) with one SELECT per table
        instead of one per track; flushes, caller commits. Per-track lookups
        were a large share of per-frame GIL time on cameras with 80+ tracks."""
        tracks = list(tracks)
        if not tracks:
            return
        existing_tracks = {
            row.track_uuid: row
            for row in self.session.query(TrackModel).filter(
                TrackModel.track_uuid.in_([t.track_uuid for t in tracks])
            )
        }
        vehicles = [t for t in tracks if t.object_type in vehicle_types]
        existing_vehicles = {
            row.track_uuid: row
            for row in self.session.query(VehicleProfileModel).filter(
                VehicleProfileModel.track_uuid.in_([t.track_uuid for t in vehicles])
            )
        } if vehicles else {}
        for track in tracks:
            row = existing_tracks.get(track.track_uuid)
            if row is None:
                row = self._new_track_row(track)
                self.session.add(row)
            self._apply_track_fields(row, track)
        for track in vehicles:
            row = existing_vehicles.get(track.track_uuid)
            if row is None:
                row = self._new_vehicle_row(track)
                self.session.add(row)
            self._apply_vehicle_fields(row, track)
        self.session.flush()

    @staticmethod
    def _new_vehicle_row(track) -> VehicleProfileModel:
        return VehicleProfileModel(
            track_uuid=track.track_uuid, camera_id=track.camera_id,
            vehicle_class=track.object_type,
            first_seen=datetime.utcfromtimestamp(track.first_seen),
            last_seen=datetime.utcfromtimestamp(track.last_seen),
        )

    @staticmethod
    def _apply_vehicle_fields(row: VehicleProfileModel, track) -> None:
        from src.features.vehicle_description import describe_vehicle

        row.last_seen = datetime.utcfromtimestamp(track.last_seen)
        row.track_duration = track.duration
        row.direction = track.movement_direction
        row.best_confidence = max(row.best_confidence or 0.0, track.confidence)
        row.best_snapshot = track.best_snapshot_path
        row.color = track.color
        row.plate = track.license_plate.upper() if track.license_plate else "UNKNOWN"
        row.plate_confidence = track.plate_confidence
        row.threat_score = track.risk_score
        row.watchlist_status = str(getattr(track, "watchlist_status", "none")).upper()
        row.description = describe_vehicle(track)
        row.zone_history = [
            {"zone_id": zone_id, "session_id": session_id, "entered_at": track.zone_entry_times.get(zone_id)}
            for zone_id, session_id in track.zone_session_ids.items()
        ]

    def upsert_vehicle_profile(self, track, commit: bool = True) -> VehicleProfileModel:
        row = self.session.query(VehicleProfileModel).filter_by(track_uuid=track.track_uuid).first()
        if row is None:
            row = self._new_vehicle_row(track)
            self.session.add(row)
        self._apply_vehicle_fields(row, track)
        if commit:
            self.session.commit()
        else:
            self.session.flush()
        return row

    def get_incident_notes(self, alert_id: str) -> list[IncidentNoteModel]:
        return (
            self.session.query(IncidentNoteModel)
            .filter_by(alert_id=alert_id)
            .order_by(IncidentNoteModel.created_at.asc())
            .all()
        )

    def create_operator_feedback(self, alert: AlertModel, operator: str, reason: str) -> OperatorFeedbackModel:
        existing = self.session.query(OperatorFeedbackModel).filter_by(
            alert_id=alert.alert_id, operator=operator, reason=reason
        ).first()
        if existing:
            return existing
        row = OperatorFeedbackModel(
            event_id=alert.event_id, alert_id=alert.alert_id, operator=operator,
            reason=reason, camera_id=alert.camera_id, event_type=alert.event_type,
            model_confidence=alert.risk_score,
            track_information={"track_id": alert.track_id, "object_type": alert.object_type},
        )
        self.session.add(row)
        self.session.flush()
        return row

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

    # ======================== WATCHLISTS ========================

    def create_watchlist_entry(
        self,
        kind: str,
        list_type: str,
        label: str,
        created_by: str,
        plate: str | None = None,
        embedding=None,
        notes: str = "",
    ) -> WatchlistEntryModel:
        import uuid

        from src.watchlist import crypto
        from src.watchlist.service import LIST_TYPES, normalize_plate

        if list_type not in LIST_TYPES:
            raise ValueError(f"list_type must be one of {LIST_TYPES}")
        row = WatchlistEntryModel(
            entry_id=f"WL_{uuid.uuid4().hex[:16]}", kind=kind, list_type=list_type,
            label=label, notes=notes or "", created_by=created_by, active=True,
        )
        if kind == "plate":
            row.plate = normalize_plate(plate)
            if not 4 <= len(row.plate) <= 20:
                raise ValueError("plate must have 4-20 letters/digits")
            clash = self.session.query(WatchlistEntryModel).filter_by(kind="plate", plate=row.plate, active=True)
            if clash.first() is not None:
                raise ValueError("this plate is already on an active watchlist")
        elif kind == "face":
            if embedding is None:
                raise ValueError("a face entry needs an embedding")
            row.embedding_enc = crypto.encrypt_embedding(embedding)
        else:
            raise ValueError("kind must be 'face' or 'plate'")
        self.session.add(row)
        self.session.commit()
        return row

    def list_watchlist_entries(self, kind: str | None = None, include_inactive: bool = False):
        query = self.session.query(WatchlistEntryModel)
        if kind:
            query = query.filter_by(kind=kind)
        if not include_inactive:
            query = query.filter_by(active=True)
        return query.order_by(desc(WatchlistEntryModel.created_at)).all()

    def deactivate_watchlist_entry(self, entry_id: str, actor: str) -> bool:
        row = self.session.query(WatchlistEntryModel).filter_by(entry_id=entry_id, active=True).first()
        if row is None:
            return False
        row.active = False
        row.deactivated_by = actor
        row.deactivated_at = datetime.utcnow()
        self.session.commit()
        return True

    def create_audit_log(self, action: str, username: str, details: dict = None, ip_address: str = None):
        log = AuditLogModel(action=action, username=username, details=details or {}, ip_address=ip_address)
        self.session.add(log)
        self.session.commit()

    def get_audit_logs(self, limit: int = 100, actions_only: bool = False) -> list[AuditLogModel]:
        """actions_only: skip the raw per-request trail ("PATCH /api/..."), keep named actions."""
        query = self.session.query(AuditLogModel)
        if actions_only:
            query = query.filter(~AuditLogModel.action.like("% /%"))
        return query.order_by(desc(AuditLogModel.timestamp)).limit(limit).all()

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
            trigger_classes=zone_data.get("trigger_classes") or None,
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

    def update_zone(self, zone_id: str, changes: dict) -> ZoneModel | None:
        zone = self.session.query(ZoneModel).filter_by(zone_id=zone_id, deleted=False).first()
        if zone is None:
            return None
        mapping = {"camera_id": "camera_id", "name": "name", "type": "zone_type", "points": "points", "color": "color", "enabled": "enabled",
                   "trigger_classes": "trigger_classes"}
        for source, target in mapping.items():
            if source in changes:
                setattr(zone, target, changes[source])
        zone.updated_at = datetime.utcnow()
        self.session.commit()
        return zone

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
        open_alerts = alerts.join(EventModel, AlertModel.event_id == EventModel.event_id).filter(
            AlertModel.status.in_(("open", "acknowledged", "investigating", "reopened")),
            EventModel.state.in_(("OPEN", "ACTIVE")),
        )
        unreviewed = open_alerts.count()
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
            "critical_alerts": open_alerts.filter(AlertModel.risk_level.in_(("critical", "high"))).count(),
        }

    def get_alert_timeseries(self, hours: int = 24, allowed_cameras=None) -> dict:
        """Return persisted alert counts in stable hourly buckets."""
        from datetime import timedelta

        now = datetime.utcnow()
        start = now - timedelta(hours=hours)
        query = self.session.query(AlertModel.timestamp).filter(AlertModel.timestamp >= start)
        if allowed_cameras is not None:
            query = query.filter(AlertModel.camera_id.in_(allowed_cameras or ["__none__"]))
        buckets = [0] * hours
        for (timestamp,) in query.all():
            age = int((now - timestamp).total_seconds() // 3600)
            if 0 <= age < hours:
                buckets[hours - 1 - age] += 1
        labels = [
            (now - timedelta(hours=hours - 1 - index)).strftime("%H:00")
            for index in range(hours)
        ]
        return {"labels": labels, "data": buckets}

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
