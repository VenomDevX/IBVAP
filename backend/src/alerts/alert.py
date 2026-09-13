"""
IBVAP — Alert Data Class
Structured alert output format.
"""

from dataclasses import dataclass, field


@dataclass
class Alert:
    """A generated security alert."""

    alert_id: str
    camera_id: str
    event_id: str
    track_id: int
    timestamp: float
    event_type: str
    risk_score: float
    risk_level: str  # "low", "medium", "high", "critical"
    object_type: str
    track_uuid: str = ""
    contributing_factors: list[str] = field(default_factory=list)
    snapshot_path: str | None = None
    snapshot_hash: str | None = None
    plate_result: str | None = None
    identity_result: str | None = None
    reviewed: bool = False
    reviewed_by: str | None = None
    reviewed_at: float | None = None

    @property
    def severity_emoji(self) -> str:
        return {
            "low": "🟢",
            "medium": "🟡",
            "high": "🟠",
            "critical": "🔴",
        }.get(self.risk_level, "⚪")

    def to_dict(self) -> dict:
        return {
            "alert_id": self.alert_id,
            "camera_id": self.camera_id,
            "event_id": self.event_id,
            "track_id": self.track_id,
            "track_uuid": self.track_uuid,
            "timestamp": self.timestamp,
            "event_type": self.event_type,
            "risk_score": round(self.risk_score, 1),
            "risk_level": self.risk_level,
            "object_type": self.object_type,
            "contributing_factors": self.contributing_factors,
            "snapshot_path": self.snapshot_path,
            "snapshot_hash": self.snapshot_hash,
            "plate_result": self.plate_result,
            "identity_result": self.identity_result,
            "reviewed": self.reviewed,
            "reviewed_by": self.reviewed_by,
            "reviewed_at": self.reviewed_at,
        }
