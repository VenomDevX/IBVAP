"""
IBVAP — Alert Engine
Generates, deduplicates, and manages security alerts.
"""

import time
import os
from typing import Dict, List, Optional, Callable
from collections import defaultdict, deque

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
    ):
        self.cooldown_seconds = cooldown_seconds
        self.max_alerts_per_minute = max_alerts_per_minute
        self.min_risk_score = min_risk_score
        self.snapshots_dir = snapshots_dir

        self._alert_counter: int = 0
        self._alerts = deque(maxlen=5000)
        self._recent_alerts: Dict[str, float] = {}  # dedup key -> timestamp
        self._rate_counter: Dict[str, list] = defaultdict(list)  # camera_id -> [timestamps]
        self._notification_callbacks: List[Callable] = []

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
        frame: Optional[np.ndarray] = None,
    ) -> Optional[Alert]:
        """
        Generate an alert from a fused event.
        Applies deduplication, rate limiting, and minimum risk threshold.
        """
        now = time.time()

        cutoff = now - self.cooldown_seconds
        self._recent_alerts = {k: t for k, t in self._recent_alerts.items() if t > cutoff}

        # --- Check minimum risk ---
        if fused_event.risk_score < self.min_risk_score:
            return None

        # --- Deduplication ---
        dedup_key = f"{fused_event.track_id}_{fused_event.event_type}"
        if dedup_key in self._recent_alerts:
            if now - self._recent_alerts[dedup_key] < self.cooldown_seconds:
                return None

        # --- Rate limiting ---
        camera_id = fused_event.camera_id
        self._rate_counter[camera_id] = [
            t for t in self._rate_counter[camera_id] if now - t < 60
        ]
        if len(self._rate_counter[camera_id]) >= self.max_alerts_per_minute:
            logger.warning(f"Rate limit reached for camera {camera_id}")
            return None

        # --- Save evidence snapshot ---
        snapshot_path = None
        snapshot_hash = None
        if frame is not None:
            snapshot_path, snapshot_hash = self._save_snapshot(
                frame, fused_event.camera_id, fused_event.event_id
            )

        # --- Create alert ---
        self._alert_counter += 1
        alert = Alert(
            alert_id=f"ALR_{int(now)}_{self._alert_counter:04d}",
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
        )

        # Store
        self._alerts.append(alert)
        self._recent_alerts[dedup_key] = now
        self._rate_counter[camera_id].append(now)

        logger.info(
            f"{alert.severity_emoji} Alert {alert.alert_id}: "
            f"{alert.event_type} [{alert.risk_level.upper()}] "
            f"Score={alert.risk_score:.0f} Camera={alert.camera_id}"
        )

        if alert.risk_level == "critical":
            self.notification_manager.notify_critical(alert.to_dict())

        # Notify callbacks
        for callback in self._notification_callbacks:
            try:
                callback(alert.to_dict())
            except Exception as e:
                logger.error(f"Alert callback error: {e}")

        return alert

    def _save_snapshot(self, frame: np.ndarray, camera_id: str,
                       event_id: str):
        """Save an evidence snapshot image and compute its SHA-256 hash."""
        try:
            filename = f"{camera_id}_{event_id}_{int(time.time())}.jpg"
            filepath = os.path.join(self.snapshots_dir, filename)
            cv2.imwrite(filepath, frame)
            return filepath, evidence.sha256_file(filepath)
        except Exception as e:
            logger.error(f"Failed to save snapshot: {e}")
            return None, None

    def mark_reviewed(self, alert_id: str, reviewed_by: str = "operator") -> bool:
        """Mark an alert as reviewed."""
        for alert in self._alerts:
            if alert.alert_id == alert_id:
                alert.reviewed = True
                alert.reviewed_by = reviewed_by
                alert.reviewed_at = time.time()
                return True
        return False

    def get_all_alerts(self, limit: int = 100) -> List[dict]:
        return [a.to_dict() for a in reversed(self._alerts[-limit:])]

    def get_unreviewed_alerts(self) -> List[dict]:
        return [a.to_dict() for a in reversed(self._alerts) if not a.reviewed]

    def get_alerts_by_camera(self, camera_id: str, limit: int = 50) -> List[dict]:
        return [
            a.to_dict() for a in reversed(self._alerts)
            if a.camera_id == camera_id
        ][:limit]

    def get_alerts_by_level(self, level: str) -> List[dict]:
        return [a.to_dict() for a in reversed(self._alerts) if a.risk_level == level]

    def get_alert(self, alert_id: str) -> Optional[dict]:
        for a in self._alerts:
            if a.alert_id == alert_id:
                return a.to_dict()
        return None

    def get_statistics(self) -> dict:
        from collections import Counter
        levels = Counter(a.risk_level for a in self._alerts)
        types = Counter(a.event_type for a in self._alerts)
        reviewed = sum(1 for a in self._alerts if a.reviewed)
        return {
            "total_alerts": len(self._alerts),
            "unreviewed": len(self._alerts) - reviewed,
            "reviewed": reviewed,
            "by_level": dict(levels),
            "by_type": dict(types),
        }
