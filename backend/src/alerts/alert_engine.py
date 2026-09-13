"""
IBVAP — Alert Engine
Generates, deduplicates, and manages security alerts.
"""

import os
import shutil
import threading
import time
import uuid
from collections import defaultdict, deque
from collections.abc import Callable

import cv2
import numpy as np
from loguru import logger

from src.alerts import evidence
from src.alerts.alert import Alert
from src.fusion.context_fusion import FusedEvent


class AlertEngine:
    """
    Generates alerts from fused events with:
    - Deduplication (cooldown-based)
    - Rate limiting
    - Minimum risk threshold
    - Evidence snapshot capture
    - WebSocket notification callbacks
    """

    def __init__(
        self,
        cooldown_seconds: float = 60.0,
        max_alerts_per_minute: int = 10,
        min_risk_score: float = 20.0,
        snapshots_dir: str = "./outputs/snapshots",
        max_snapshots_per_hour: int = 60,
        max_snapshot_storage_mb: int = 2048,
        min_free_storage_mb: int = 1024,
    ):
        self.cooldown_seconds = cooldown_seconds
        self.max_alerts_per_minute = max_alerts_per_minute
        self.min_risk_score = min_risk_score
        self.snapshots_dir = snapshots_dir
        self.max_snapshots_per_hour = max(0, int(max_snapshots_per_hour))
        self.max_snapshot_storage_bytes = max(0, int(max_snapshot_storage_mb)) * 1024 * 1024
        self.min_free_storage_bytes = max(0, int(min_free_storage_mb)) * 1024 * 1024
        self.persistence_lock = threading.RLock()

        self._alert_counter: int = 0
        self._alerts = deque(maxlen=5000)
        self._recent_alerts: dict[str, float] = {}  # dedup key -> timestamp
        self._recent_levels: dict[str, int] = {}
        self._rate_counter: dict[str, list] = defaultdict(list)  # camera_id -> [timestamps]
        self._snapshot_counter: dict[str, deque] = defaultdict(deque)
        self._snapshot_bytes: int | None = None
        self._last_storage_warning = 0.0
        self._notification_callbacks: list[Callable] = []

        from src.alerts.notifiers import NotificationManager

        self.notification_manager = NotificationManager()

        # Ensure snapshots directory exists
        os.makedirs(self.snapshots_dir, exist_ok=True)

    def register_callback(self, callback: Callable):
        """Register a callback for new alert notifications (e.g., WebSocket push)."""
        self._notification_callbacks.append(callback)

    def generate_alert(
        self,
        fused_event: FusedEvent,
        frame: np.ndarray | None = None,
        publish: bool = True,
    ) -> Alert | None:
        """
        Generate an alert from a fused event.
        Applies deduplication, rate limiting, and minimum risk threshold.
        """
        now = time.time()

        cutoff = now - self.cooldown_seconds
        self._recent_alerts = {k: t for k, t in self._recent_alerts.items() if t > cutoff}
        self._recent_levels = {k: v for k, v in self._recent_levels.items() if k in self._recent_alerts}

        # --- Check minimum risk ---
        if fused_event.risk_score < self.min_risk_score:
            return None

        # --- Deduplication ---
        dedup_key = self._dedup_key(fused_event)
        level = self._level(fused_event.risk_level)
        escalating = dedup_key in self._recent_levels and level > self._recent_levels[dedup_key]
        if dedup_key in self._recent_alerts:
            if not escalating and now - self._recent_alerts[dedup_key] < self.cooldown_seconds:
                return None

        # --- Rate limiting ---
        camera_id = fused_event.camera_id
        self._rate_counter[camera_id] = [t for t in self._rate_counter[camera_id] if now - t < 60]
        if not escalating and len(self._rate_counter[camera_id]) >= self.max_alerts_per_minute:
            logger.warning(f"Rate limit reached for camera {camera_id}")
            return None

        # --- Save evidence snapshot ---
        snapshot_path = None
        snapshot_hash = None
        if frame is not None:
            snapshot_path, snapshot_hash = self._save_snapshot(frame, fused_event.camera_id, fused_event.event_id)

        # --- Create alert ---
        self._alert_counter += 1
        alert = Alert(
            alert_id=f"ALR_{uuid.uuid4().hex}",
            camera_id=fused_event.camera_id,
            event_id=fused_event.event_id,
            track_id=fused_event.track_id,
            timestamp=now,
            event_type=fused_event.event_type,
            risk_score=fused_event.risk_score,
            risk_level=fused_event.risk_level,
            object_type=fused_event.object_type,
            contributing_factors=fused_event.contributing_factors,
            snapshot_path=snapshot_path,
            snapshot_hash=snapshot_hash,
            plate_result=(fused_event.vehicle_context or {}).get("plate"),
            identity_result=(
                (fused_event.identity_context or {}).get("identity")
                if (fused_event.identity_context or {}).get("identity_status") not in (None, "unknown")
                else None
            ),
        )

        if publish:
            self.publish_alert(alert)
        return alert

    @staticmethod
    def _dedup_key(event) -> str:
        # Deliberately omit track_id. Trackers can churn IDs for one physical
        # incident; a new ID must not create another alert and snapshot.
        return f"{event.camera_id}:{event.object_type}:{event.event_type}"

    @staticmethod
    def _level(level: str) -> int:
        return {"low": 0, "medium": 1, "high": 2, "critical": 3}.get(level, 0)

    def publish_alert(self, alert: Alert):
        """Call only after persistence succeeds in the runtime pipeline."""
        now = time.time()
        dedup_key = self._dedup_key(alert)
        self._alerts.append(alert)
        self._recent_alerts[dedup_key] = now
        self._recent_levels[dedup_key] = self._level(alert.risk_level)
        self._rate_counter[alert.camera_id].append(now)

        logger.info(
            f"{alert.severity_emoji} Alert {alert.alert_id}: "
            f"{alert.event_type} [{alert.risk_level.upper()}] "
            f"Score={alert.risk_score:.0f} Camera={alert.camera_id}"
        )

        if alert.risk_level == "critical":
            try:
                self.notification_manager.notify_critical(alert.to_dict())
            except Exception as e:
                logger.error(f"Critical notification dispatch failed: {e}")

        # Notify callbacks
        for callback in self._notification_callbacks:
            try:
                callback(alert.to_dict())
            except Exception as e:
                logger.error(f"Alert callback error: {e}")

    def _save_snapshot(self, frame: np.ndarray, camera_id: str, event_id: str):
        """Save one atomic evidence image if storage budgets allow it."""
        now = time.time()
        camera_times = self._snapshot_counter[camera_id]
        while camera_times and now - camera_times[0] >= 3600:
            camera_times.popleft()

        if len(camera_times) >= self.max_snapshots_per_hour:
            self._warn_storage(f"snapshot hourly budget reached for {camera_id}")
            return None, None

        if self._snapshot_bytes is None:
            self._snapshot_bytes = sum(
                entry.stat().st_size
                for entry in os.scandir(self.snapshots_dir)
                if entry.is_file() and entry.name.lower().endswith((".jpg", ".jpeg", ".png"))
            )
        if self._snapshot_bytes >= self.max_snapshot_storage_bytes:
            self._warn_storage("snapshot storage budget reached")
            return None, None
        if shutil.disk_usage(self.snapshots_dir).free < self.min_free_storage_bytes:
            self._warn_storage("minimum free disk reserve reached")
            return None, None

        try:
            filename = f"{camera_id}_{event_id}_{int(time.time())}.jpg"
            filepath = os.path.join(self.snapshots_dir, filename)
            temporary = filepath + ".tmp.jpg"
            if not cv2.imwrite(temporary, frame):
                raise OSError("OpenCV could not encode the snapshot")
            os.replace(temporary, filepath)
            size = os.path.getsize(filepath)
            self._snapshot_bytes += size
            camera_times.append(now)
            return filepath, evidence.sha256_file(filepath)
        except Exception as e:
            if "temporary" in locals() and os.path.exists(temporary):
                try:
                    os.remove(temporary)
                except OSError:
                    pass
            logger.error(f"Failed to save snapshot: {e}")
            return None, None

    def _warn_storage(self, reason: str) -> None:
        now = time.time()
        if now - self._last_storage_warning >= 60:
            logger.warning("Evidence capture paused: {}", reason)
            self._last_storage_warning = now

    def get_storage_status(self) -> dict:
        if self._snapshot_bytes is None:
            self._snapshot_bytes = sum(
                entry.stat().st_size
                for entry in os.scandir(self.snapshots_dir)
                if entry.is_file() and entry.name.lower().endswith((".jpg", ".jpeg", ".png"))
            )
        used = round(self._snapshot_bytes / (1024 * 1024), 1)
        free_bytes = shutil.disk_usage(self.snapshots_dir).free
        free = round(free_bytes / (1024 * 1024), 1)
        return {
            "snapshot_storage_mb": used,
            "snapshot_storage_limit_mb": round(self.max_snapshot_storage_bytes / (1024 * 1024)),
            "free_storage_mb": free,
            "capture_enabled": (
                (self._snapshot_bytes is None or self._snapshot_bytes < self.max_snapshot_storage_bytes)
                and free_bytes >= self.min_free_storage_bytes
            ),
        }

    def mark_reviewed(self, alert_id: str, reviewed_by: str = "operator") -> bool:
        """Mark an alert as reviewed."""
        for alert in self._alerts:
            if alert.alert_id == alert_id:
                alert.reviewed = True
                alert.reviewed_by = reviewed_by
                alert.reviewed_at = time.time()
                return True
        return False

    def get_all_alerts(self, limit: int = 100) -> list[dict]:
        return [a.to_dict() for a in reversed(list(self._alerts)[-limit:])]

    def get_unreviewed_alerts(self) -> list[dict]:
        return [a.to_dict() for a in reversed(self._alerts) if not a.reviewed]

    def get_alerts_by_camera(self, camera_id: str, limit: int = 50) -> list[dict]:
        return [a.to_dict() for a in reversed(self._alerts) if a.camera_id == camera_id][:limit]

    def get_alerts_by_level(self, level: str) -> list[dict]:
        return [a.to_dict() for a in reversed(self._alerts) if a.risk_level == level]

    def get_alert(self, alert_id: str) -> dict | None:
        for a in self._alerts:
            if a.alert_id == alert_id:
                return a.to_dict()
        return None

    def get_statistics(self, allowed_cameras=None) -> dict:
        from collections import Counter

        alerts = [a for a in list(self._alerts) if allowed_cameras is None or a.camera_id in allowed_cameras]
        levels = Counter(a.risk_level for a in alerts)
        types = Counter(a.event_type for a in alerts)
        reviewed = sum(1 for a in alerts if a.reviewed)
        return {
            "total_alerts": len(alerts),
            "unreviewed": len(alerts) - reviewed,
            "reviewed": reviewed,
            "by_level": dict(levels),
            "by_type": dict(types),
        }
