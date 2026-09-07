"""
IBVAP — ML Risk Classifier (Optional)
Event-level ML classifier for comparison with rule-based baseline.
"""

from typing import List, Optional, Tuple
import numpy as np
from loguru import logger


class RiskClassifier:
    """
    Optional ML-based risk classifier.
    Trains on event-level features to classify risk levels.
    Used for experimental comparison against the rule-based risk engine.

    Possible models: XGBoost, RandomForest, LightGBM, MLP
    """

    def __init__(self, model_type: str = "random_forest"):
        self.model_type = model_type
        self._model = None
        self._feature_names = [
            "person_detected", "vehicle_detected", "night", "restricted_zone",
            "fence_crossing", "loitering", "unknown_identity", "movement_toward_fence",
            "duration_seconds", "object_count", "average_speed",
            "distance_to_boundary", "plate_detected", "identity_confidence",
        ]
        self._label_map = {0: "low", 1: "medium", 2: "high", 3: "critical"}

    def train(self, X: np.ndarray, y: np.ndarray):
        """Train the risk classifier."""
        try:
            from sklearn.ensemble import RandomForestClassifier
            from sklearn.model_selection import cross_val_score

            self._model = RandomForestClassifier(
                n_estimators=100, max_depth=10, random_state=42
            )
            self._model.fit(X, y)

            # Cross-validation score
            scores = cross_val_score(self._model, X, y, cv=5, scoring='f1_macro')
            logger.info(f"Risk classifier trained — CV F1: {scores.mean():.3f} ± {scores.std():.3f}")

        except ImportError:
            logger.error("scikit-learn not installed — ML risk classifier unavailable")
        except Exception as e:
            logger.error(f"Training error: {e}")

    def predict(self, features: dict) -> Tuple[str, float]:
        """
        Predict risk level from event features.

        Returns:
            (risk_level, confidence)
        """
        if self._model is None:
            return ("low", 0.0)

        try:
            X = np.array([[features.get(f, 0) for f in self._feature_names]])
            pred = self._model.predict(X)[0]
            proba = self._model.predict_proba(X)[0]
            confidence = float(np.max(proba))
            risk_level = self._label_map.get(int(pred), "low")
            return (risk_level, confidence)
        except Exception as e:
            logger.error(f"Prediction error: {e}")
            return ("low", 0.0)

    def extract_features(self, fused_event) -> dict:
        """Extract feature vector from a FusedEvent for ML classification."""
        spatial = fused_event.spatial_context or {}
        temporal = fused_event.temporal_context or {}
        identity = fused_event.identity_context or {}

        return {
            "person_detected": 1 if fused_event.object_type == "person" else 0,
            "vehicle_detected": 1 if fused_event.object_type in ("car", "truck", "bus", "motorcycle") else 0,
            "night": 1 if temporal.get("is_night", False) else 0,
            "restricted_zone": 1 if spatial.get("in_restricted", False) else 0,
            "fence_crossing": 1 if spatial.get("fence_crossed", False) else 0,
            "loitering": 1 if temporal.get("is_loitering", False) else 0,
            "unknown_identity": 1 if identity.get("identity") == "unknown" else 0,
            "movement_toward_fence": 1 if "Moving toward restricted" in str(fused_event.contributing_factors) else 0,
            "duration_seconds": fused_event.duration,
            "object_count": 1,
            "average_speed": 0.0,
            "distance_to_boundary": 0.0,
            "plate_detected": 0,
            "identity_confidence": identity.get("similarity", 0.0),
        }
