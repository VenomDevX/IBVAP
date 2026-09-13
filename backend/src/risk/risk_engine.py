"""
IBVAP — Risk Engine
Weighted risk scoring: R = w1*S + w2*T + w3*B + w4*I + w5*V
Produces explainable risk scores with human-readable reasons.
"""

from src.fusion.context_fusion import FusedEvent


class RiskEngine:
    """
    Interpretable rule-based risk scoring engine.

    Formula: R = w1*S + w2*T + w3*B + w4*I + w5*V
    Where:
        S = Spatial risk (zone proximity, zone entry, fence crossing)
        T = Temporal risk (night-time, loitering duration)
        B = Behavioral risk (direction, speed, trajectory anomaly)
        I = Identity-related context
        V = Vehicle-related context
    """

    def __init__(self, config: dict):
        weights = config.get("weights", {})
        self.w_spatial = weights.get("spatial", 0.30)
        self.w_temporal = weights.get("temporal", 0.20)
        self.w_behavioral = weights.get("behavioral", 0.25)
        self.w_identity = weights.get("identity", 0.15)
        self.w_vehicle = weights.get("vehicle", 0.10)

        # Risk level thresholds
        levels = config.get("levels", {})
        self.level_low = levels.get("low", 25)
        self.level_medium = levels.get("medium", 50)
        self.level_high = levels.get("high", 75)

        # Score tables
        self.spatial_scores = config.get("spatial_scores", {})
        self.temporal_scores = config.get("temporal_scores", {})
        self.behavioral_scores = config.get("behavioral_scores", {})
        self.identity_scores = config.get("identity_scores", {})
        self.vehicle_scores = config.get("vehicle_scores", {})
        # Minimum behavioural risk implied by the detected object class itself
        self.object_scores = config.get("object_scores", {})

    def calculate_risk(self, fused_event: FusedEvent) -> tuple[float, str, list[str]]:
        """
        Calculate risk score for a fused event.

        Returns:
            (risk_score: 0-100, risk_level: str, reasons: [str])
        """
        reasons = []

        # --- S: Spatial Risk ---
        s_score, s_reasons = self._calculate_spatial_risk(fused_event.spatial_context)
        reasons.extend(s_reasons)

        # --- T: Temporal Risk ---
        t_score, t_reasons = self._calculate_temporal_risk(fused_event.temporal_context)
        reasons.extend(t_reasons)

        # --- B: Behavioral Risk ---
        b_score, b_reasons = self._calculate_behavioral_risk(
            fused_event.event_type,
            fused_event.contributing_factors,
            fused_event.object_type,
        )
        reasons.extend(b_reasons)

        # --- I: Identity Risk ---
        i_score, i_reasons = self._calculate_identity_risk(fused_event.identity_context)
        reasons.extend(i_reasons)

        # --- V: Vehicle Risk ---
        v_score, v_reasons = self._calculate_vehicle_risk(fused_event.vehicle_context)
        reasons.extend(v_reasons)

        # Weighted combination
        risk_score = (
            self.w_spatial * s_score
            + self.w_temporal * t_score
            + self.w_behavioral * b_score
            + self.w_identity * i_score
            + self.w_vehicle * v_score
        )

        # Clamp to 0-100
        risk_score = max(0.0, min(100.0, risk_score))

        # Determine risk level
        risk_level = self._score_to_level(risk_score)

        return risk_score, risk_level, reasons

    def calculate_breakdown(self, fused_event: FusedEvent) -> dict:
        """Return one normalized contribution per semantic factor category."""
        s_score, s_reasons = self._calculate_spatial_risk(fused_event.spatial_context)
        t_score, t_reasons = self._calculate_temporal_risk(fused_event.temporal_context)
        b_score, b_reasons = self._calculate_behavioral_risk(
            fused_event.event_type, fused_event.contributing_factors, fused_event.object_type
        )
        i_score, i_reasons = self._calculate_identity_risk(fused_event.identity_context)
        v_score, v_reasons = self._calculate_vehicle_risk(fused_event.vehicle_context)
        rows = {
            "zone": (s_score, self.w_spatial, s_reasons),
            "time": (t_score, self.w_temporal, t_reasons),
            "behavior": (b_score, self.w_behavioral, b_reasons),
            "identity": (i_score, self.w_identity, i_reasons),
            "vehicle": (v_score, self.w_vehicle, v_reasons),
        }
        return {
            category: {
                "raw_score": round(raw, 2),
                "weight": weight,
                "contribution": round(raw * weight, 2),
                "reasons": list(dict.fromkeys(reasons)),
            }
            for category, (raw, weight, reasons) in rows.items()
        }

    def score_fused_event(self, fused_event: FusedEvent) -> FusedEvent:
        """Calculate and attach risk score to a fused event."""
        score, level, reasons = self.calculate_risk(fused_event)
        fused_event.risk_score = score
        fused_event.risk_level = level
        fused_event.score_breakdown = self.calculate_breakdown(fused_event)
        # The structured breakdown is authoritative. Flatten its already
        # normalized reasons only for backwards-compatible UI/report display.
        fused_event.contributing_factors = list(dict.fromkeys(
            reason
            for category in fused_event.score_breakdown.values()
            for reason in category["reasons"]
        ))
        return fused_event

    def _calculate_spatial_risk(self, ctx: dict) -> tuple[float, list[str]]:
        """Calculate spatial component of risk."""
        score = 0.0
        reasons = []

        if ctx.get("in_restricted", False):
            score = max(score, self.spatial_scores.get("in_restricted_zone", 90))
            reasons.append("Inside restricted zone")

        if ctx.get("fence_crossed", False):
            score = max(score, self.spatial_scores.get("fence_crossed", 95))
            reasons.append("Virtual fence crossed")

        if ctx.get("in_buffer", False):
            score = max(score, self.spatial_scores.get("in_buffer_zone", 50))
            reasons.append("Inside buffer zone")

        if ctx.get("approaching_fence", False):
            score = max(score, self.spatial_scores.get("approaching_fence", 60))
            reasons.append("Approaching fence boundary")

        return score, reasons

    def _calculate_temporal_risk(self, ctx: dict) -> tuple[float, list[str]]:
        """Calculate temporal component of risk."""
        score = 0.0
        reasons = []

        if ctx.get("is_night", False):
            score = max(score, self.temporal_scores.get("night_time", 40))
            reasons.append("Night-time conditions")

        duration = ctx.get("loiter_duration", 0)
        if duration >= 120:
            score = max(score, self.temporal_scores.get("loitering_120s", 90))
            reasons.append(f"Loitering for {duration:.0f}s (extended)")
        elif duration >= 60:
            score = max(score, self.temporal_scores.get("loitering_60s", 70))
            reasons.append(f"Loitering for {duration:.0f}s")
        elif duration >= 30:
            score = max(score, self.temporal_scores.get("loitering_30s", 50))
            reasons.append(f"Loitering for {duration:.0f}s")

        return score, reasons

    def _calculate_behavioral_risk(
        self, event_type: str, factors: list[str], object_type: str = ""
    ) -> tuple[float, list[str]]:
        """Calculate behavioral component of risk."""
        score = 0.0
        reasons = []

        # Score based on event type
        type_scores = {
            "critical_intrusion": 95,
            "combined_suspicious_activity": 85,
            "night_fence_crossing": 90,
            "fence_crossing": 80,
            "restricted_zone_loitering": 75,
            "night_restricted_zone_entry": 80,
            "restricted_zone_entry": 70,
            "night_loitering": 60,
            "loitering": 50,
            "night_movement": 40,
            "boundary_approach": 45,
            "unexpected_direction": 50,
            "general_activity": 10,
        }

        score = type_scores.get(event_type, 10)

        if "Moving toward restricted zone" in factors:
            score = max(score, self.behavioral_scores.get("toward_restricted", 60))
            reasons.append("Moving toward restricted area")

        if "Virtual fence crossed" in factors:
            reasons.append("Boundary violation detected")

        # Object-class floor — a tank or aircraft near a monitored boundary is
        # inherently higher-risk than a pedestrian doing the same thing.
        obj_scores = self.object_scores or {}
        obj_floor = obj_scores.get((object_type or "").lower())
        if obj_floor:
            score = max(score, float(obj_floor))
            reasons.append(f"High-interest object class: {object_type.replace('_', ' ')}")

        context_only_types = {
            "restricted_zone_entry", "night_restricted_zone_entry", "restricted_zone_loitering",
            "loitering", "night_loitering", "fence_crossing", "night_fence_crossing",
        }
        if not reasons and event_type not in context_only_types:
            reasons.append(f"Behavioral pattern: {event_type.replace('_', ' ')}")

        return score, reasons

    def _calculate_identity_risk(self, ctx: dict) -> tuple[float, list[str]]:
        """Calculate identity component of risk."""
        score = 0.0
        reasons = []

        identity = ctx.get("identity_status", ctx.get("identity", "not_checked"))

        if identity == "unknown":
            score = self.identity_scores.get("unknown_person", 60)
            reasons.append("Unknown person identity")
        elif identity == "uncertain":
            score = self.identity_scores.get("uncertain_match", 40)
            reasons.append("Uncertain identity match")
        elif identity == "known":
            score = self.identity_scores.get("known_authorized", 0)

        return score, reasons

    def _calculate_vehicle_risk(self, ctx: dict) -> tuple[float, list[str]]:
        """Calculate vehicle component of risk."""
        score = 0.0
        reasons = []

        plate = ctx.get("plate_status", str(ctx.get("plate", "not_checked")).lower())

        if plate == "unknown":
            score = self.vehicle_scores.get("unknown_plate", 50)
            reasons.append("Unknown vehicle plate")
        elif plate == "low_confidence":
            score = self.vehicle_scores.get("plate_read_low_confidence", 35)
            reasons.append("Low confidence plate reading")
        elif plate == "not_detected":
            score = self.vehicle_scores.get("no_plate_detected", 30)
            reasons.append("No plate detected")

        return score, reasons

    def _score_to_level(self, score: float) -> str:
        """Convert numeric score to risk level."""
        if score >= self.level_high:
            return "critical"
        elif score >= self.level_medium:
            return "high"
        elif score >= self.level_low:
            return "medium"
        return "low"

    def get_explainable_summary(self, fused_event: FusedEvent) -> str:
        """Generate a human-readable risk summary."""
        lines = [
            f"{'=' * 50}",
            f"  {fused_event.risk_level.upper()} RISK EVENT",
            f"{'=' * 50}",
            f"  Risk Score: {fused_event.risk_score:.0f}/100",
            f"  Event Type: {fused_event.event_type.replace('_', ' ').title()}",
            f"  Object: {fused_event.object_type} (Track ID: {fused_event.track_id})",
            f"  Camera: {fused_event.camera_id}",
            "",
            "  Contributing Factors:",
        ]

        for factor in fused_event.contributing_factors:
            lines.append(f"    ✓ {factor}")

        if fused_event.duration > 0:
            lines.append("")
            lines.append(f"  Duration: {fused_event.duration:.0f} seconds")

        lines.append(f"{'=' * 50}")

        return "\n".join(lines)
