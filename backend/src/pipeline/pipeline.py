"""
IBVAP — Video Processing Pipeline
Main orchestrator: Ingest → Detect → Track → Spatial → Temporal → Behavior → Fusion → Risk → Alert → Store
"""

import os
import threading
import time
from pathlib import Path

import numpy as np
import yaml
from loguru import logger

from src.alerts.alert_engine import AlertEngine
from src.behavior.behavior_engine import BehaviorEngine
from src.database.db import get_database
from src.database.repository import Repository
from src.detection.detector import ObjectDetector
from src.features.anpr import extract_license_plate
from src.features.color_extractor import get_dominant_color
from src.fusion.context_fusion import ContextFusion
from src.ingestion.video_source import CameraInfo, VideoSource
from src.risk.risk_engine import RiskEngine
from src.spatial.direction_analyzer import DirectionAnalyzer
from src.spatial.fence_detector import FenceDetector
from src.spatial.heatmap_tracker import HeatmapTracker
from src.spatial.zone_manager import ZoneManager
from src.temporal.loitering_detector import LoiteringDetector
from src.temporal.night_detector import NightDetector
from src.tracking.track_manager import TrackManager
from src.tracking.tracker import MultiObjectTracker


class CameraPipeline:
    """Processing pipeline for a single camera source."""

    def __init__(
        self,
        camera_info: CameraInfo,
        detector: ObjectDetector,
        zone_manager: ZoneManager,
        fence_detector: FenceDetector,
        risk_config: dict,
        alert_engine: AlertEngine,
    ):
        self.camera_info = camera_info
        self.video_source = VideoSource(camera_info)
        self.detector = detector  # Shared detector across cameras
        self.tracker = MultiObjectTracker()
        self.track_manager = TrackManager()
        self.heatmap_tracker = HeatmapTracker()
        self.zone_manager = zone_manager
        self.fence_detector = fence_detector
        self.direction_analyzer = DirectionAnalyzer()
        self.loitering_detector = LoiteringDetector()
        self.night_detector = NightDetector()
        self.behavior_engine = BehaviorEngine()
        self.context_fusion = ContextFusion()
        self.risk_engine = RiskEngine(risk_config)
        self.alert_engine = alert_engine

        self._running = False
        self._thread: threading.Thread | None = None
        self._latest_frame: np.ndarray | None = None
        self._latest_annotated: np.ndarray | None = None
        self._frame_lock = threading.Lock()
        self._stats = {
            "frames_processed": 0,
            "detections": 0,
            "active_tracks": 0,
            "events_generated": 0,
            "alerts_generated": 0,
            "fps": 0.0,
        }

    def start(self):
        """Start the processing pipeline in a background thread."""
        if self._running:
            return

        if not self.video_source.connect():
            logger.error(f"Failed to start pipeline for {self.camera_info.camera_id}")
            return

        self._running = True
        self._thread = threading.Thread(target=self._process_loop, daemon=True)
        self._thread.start()
        logger.info(f"Pipeline started for {self.camera_info.camera_id}")

    def stop(self):
        """Stop the processing pipeline."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        self.video_source.release()
        logger.info(f"Pipeline stopped for {self.camera_info.camera_id}")

    def _process_loop(self):
        """Main processing loop."""
        while self._running:
            try:
                start_time = time.time()

                # 1. Read frame
                ret, frame = self.video_source.read_frame()
                if not ret or frame is None:
                    if not self.video_source.is_stream():
                        # Video file ended
                        logger.info(f"Video file ended for {self.camera_info.camera_id}")
                        self._running = False
                        break
                    # Stream error — try reconnect
                    if not self.video_source.reconnect():
                        self._running = False
                        break
                    continue

                frame_id = self.video_source.frame_id
                camera_id = self.camera_info.camera_id

                # Store raw frame
                with self._frame_lock:
                    self._latest_frame = frame.copy()

                # 2. Detect objects
                detections = self.detector.detect(frame, frame_id, camera_id)
                self._stats["detections"] = len(detections.detections)

                # 3. Track objects
                active_tracks = self.tracker.update(detections)
                self.track_manager.update_tracks(active_tracks)
                self.heatmap_tracker.add_points(active_tracks)
                self._stats["active_tracks"] = len(active_tracks)

                # 4-9. Process each active track
                for tid, track in active_tracks.items():
                    # Extract features if needed
                    if track.duration > 0.5:
                        x1, y1, x2, y2 = [int(v) for v in track.bbox]
                        # Ensure bounds
                        x1 = max(0, x1)
                        y1 = max(0, y1)
                        x2 = min(frame.shape[1], x2)
                        y2 = min(frame.shape[0], y2)

                        if x2 > x1 and y2 > y1:
                            crop = frame[y1:y2, x1:x2]
                            if track.color == "Unknown":
                                track.color = get_dominant_color(crop)
                            if (
                                track.object_type in ("car", "truck", "bus", "motorcycle", "vehicle")
                                and track.license_plate == "Unknown"
                            ):
                                track.license_plate = extract_license_plate(crop)

                    self._process_track(track, frame)

                # Annotate frame
                annotated = frame.copy()
                # Draw zones
                camera_zones = self.zone_manager.get_camera_zones(camera_id)
                if camera_zones:
                    annotated = ZoneManager.draw_zones(annotated, camera_zones)
                # Draw fences
                fences = [f for f in self.fence_detector._fences.values() if f.camera_id == camera_id]
                if fences:
                    annotated = FenceDetector.draw_fences(annotated, fences)
                # Draw tracks
                annotated = MultiObjectTracker.draw_tracks(annotated, active_tracks)

                with self._frame_lock:
                    self._latest_annotated = annotated

                # Update stats
                self._stats["frames_processed"] += 1
                elapsed = time.time() - start_time
                self._stats["fps"] = 1.0 / elapsed if elapsed > 0 else 0.0

            except Exception as e:
                logger.error(f"Pipeline error ({self.camera_info.camera_id}): {e}")
                time.sleep(0.1)

    def _process_track(self, track, frame: np.ndarray):
        """Process a single track through spatial/temporal/behavior/fusion/risk pipeline."""
        camera_id = track.camera_id
        cx, cy = track.centroid

        # 4. Spatial analysis
        current_zone_ids = self.zone_manager.check_track_zones(camera_id, (cx, cy))
        track.current_zones = current_zone_ids
        in_restricted = self.zone_manager.is_in_restricted_zone(camera_id, cx, cy)

        spatial_context = {
            "in_restricted": in_restricted,
            "in_buffer": any(
                self.zone_manager.get_zone(zid).zone_type == "buffer"
                for zid in current_zone_ids
                if self.zone_manager.get_zone(zid)
            ),
            "zones": current_zone_ids,
            "fence_crossed": track.has_crossed_fence,
        }

        # Check fence crossing
        fence_events = self.fence_detector.check_crossing(track)
        approaching = self.fence_detector.check_approaching(track)

        fence_context = {
            "crossed": len(fence_events) > 0,
            "approaching": len(approaching) > 0,
            "fence_id": fence_events[0].fence_id if fence_events else "",
            "crossing_direction": fence_events[0].direction if fence_events else "",
            "distance": approaching[0]["distance"] if approaching else 0,
            "fence_name": approaching[0]["fence_name"] if approaching else "",
        }

        if fence_events:
            spatial_context["fence_crossed"] = True

        # 5. Direction analysis
        direction = self.direction_analyzer.analyze_direction(track)
        track.movement_direction = direction
        toward_restricted = False
        for zone in self.zone_manager.get_camera_zones(camera_id):
            if zone.zone_type == "restricted":
                zone_center = (int(np.mean([p[0] for p in zone.points])), int(np.mean([p[1] for p in zone.points])))
                if self.direction_analyzer.is_moving_toward_zone(track, zone_center):
                    toward_restricted = True
                    break

        direction_context = {
            "direction": direction,
            "toward_restricted": toward_restricted,
        }

        # 6. Temporal analysis
        loiter_events = self.loitering_detector.check_loitering(track, current_zone_ids)
        night_ctx = self.night_detector.get_night_context(frame)

        temporal_context = {
            "is_night": night_ctx.get("is_night", False),
            "is_night_time": night_ctx.get("is_night_time", False),
            "is_loitering": len(loiter_events) > 0 or track.is_loitering,
            "loiter_duration": loiter_events[0].duration if loiter_events else 0,
            "loiter_zone": loiter_events[0].zone_id if loiter_events else "",
            "brightness": night_ctx.get("brightness", 128),
        }

        # 7. Behavior analysis
        behavior_events = self.behavior_engine.analyze_track(
            track, spatial_context, temporal_context, direction_context, fence_context
        )

        if not behavior_events:
            return

        # 8. Context fusion
        identity_context = {}
        if track.color != "Unknown":
            identity_context["color"] = track.color

        vehicle_context = {}
        if hasattr(track, "license_plate") and track.license_plate != "Unknown":
            vehicle_context["plate"] = track.license_plate

        fused_event = self.context_fusion.fuse_events(
            track_id=track.track_id,
            camera_id=camera_id,
            object_type=track.object_type,
            behavior_events=behavior_events,
            spatial_context=spatial_context,
            temporal_context=temporal_context,
            identity_context=identity_context,
            vehicle_context=vehicle_context,
            track_duration=track.duration,
        )

        if fused_event is None:
            return

        # 9. Risk scoring
        fused_event = self.risk_engine.score_fused_event(fused_event)

        # Attach latest risk to the track for live dashboard
        track.risk_score = fused_event.risk_score
        track.risk_level = fused_event.risk_level
        track.risk_factors = fused_event.contributing_factors

        # Print risk summary for significant events
        if fused_event.risk_level in ("high", "critical"):
            summary = self.risk_engine.get_explainable_summary(fused_event)
            logger.info(f"\n{summary}")

        # 10. Alert generation
        alert = self.alert_engine.generate_alert(fused_event, frame)

        if alert:
            self._stats["alerts_generated"] += 1
            if alert.snapshot_path:
                fused_event.evidence_path = alert.snapshot_path
                fused_event.evidence_hash = alert.snapshot_hash

            # Store to database
            try:
                db = get_database()
                session = db.get_session()
                repo = Repository(session)
                repo.create_event(fused_event.to_dict())
                repo.create_alert(alert.to_dict())
                session.close()
            except Exception as e:
                logger.error(f"Database write error: {e}")

        self._stats["events_generated"] += 1

    def get_latest_frame(self) -> np.ndarray | None:
        """Get the latest raw frame."""
        with self._frame_lock:
            return self._latest_frame.copy() if self._latest_frame is not None else None

    def get_latest_annotated_frame(self) -> np.ndarray | None:
        """Get the latest annotated frame (with overlays)."""
        with self._frame_lock:
            return self._latest_annotated.copy() if self._latest_annotated is not None else None

    def get_stats(self) -> dict:
        return {
            **self._stats,
            "camera_status": self.video_source.status.value,
            "camera_id": self.camera_info.camera_id,
        }


class IBVAPPipeline:
    """
    Master pipeline managing multiple camera pipelines.
    Entry point for the IBVAP processing system.
    """

    def __init__(self, config_dir: str = "./configs"):
        self.config_dir = Path(config_dir)
        self.camera_pipelines: dict[str, CameraPipeline] = {}
        self.detector: ObjectDetector | None = None
        self.zone_manager = ZoneManager()
        self.fence_detector = FenceDetector()
        self.alert_engine = AlertEngine()
        self._risk_config = {}

    def initialize(self):
        """Load configs and initialize all components."""
        logger.info("Initializing IBVAP Pipeline...")

        # Load configurations
        cameras_config = self._load_yaml("cameras.yaml")
        zones_config = self._load_yaml("zones.yaml")
        thresholds_config = self._load_yaml("thresholds.yaml")
        self._risk_config = self._load_yaml("risk_weights.yaml")

        # Initialize detector (shared across cameras)
        det_cfg = thresholds_config.get("detection", {})
        weights_path = det_cfg.get("weights_path") or ""
        use_custom = bool(weights_path) and os.path.exists(weights_path)
        if weights_path and not use_custom:
            logger.warning(f"detection.weights_path set but not found ({weights_path}) - using stock model")
        self.detector = ObjectDetector(
            model_path=weights_path if use_custom else det_cfg.get("model_variant", "yolov8n") + ".pt",
            confidence_threshold=det_cfg.get("confidence_threshold", 0.40),
            target_classes=det_cfg.get("target_classes") or [0, 2, 3, 5, 7],
            imgsz=det_cfg.get("imgsz", 640),
            detect_all=use_custom,  # custom coarse model: emit all its classes
        )

        # Initialize zones
        self.zone_manager.load_from_config(zones_config)

        # Initialize fences
        self.fence_detector.load_from_config(zones_config)

        # Initialize alert engine
        alert_cfg = thresholds_config.get("alerts", {})
        self.alert_engine = AlertEngine(
            cooldown_seconds=alert_cfg.get("cooldown_seconds", 60),
            max_alerts_per_minute=alert_cfg.get("max_alerts_per_minute", 10),
            min_risk_score=alert_cfg.get("min_alert_risk_score", 20),
        )

        # Initialize database
        db = get_database()

        # Initialize camera pipelines
        for cam_cfg in cameras_config.get("cameras", []):
            if not cam_cfg.get("enabled", True):
                continue

            camera_info = CameraInfo(
                camera_id=cam_cfg["id"],
                name=cam_cfg["name"],
                source=cam_cfg["source"],
                camera_type=cam_cfg.get("type", "general"),
                fps_limit=cam_cfg.get("fps_limit", 15),
            )

            pipeline = CameraPipeline(
                camera_info=camera_info,
                detector=self.detector,
                zone_manager=self.zone_manager,
                fence_detector=self.fence_detector,
                risk_config=self._risk_config,
                alert_engine=self.alert_engine,
            )

            self.camera_pipelines[camera_info.camera_id] = pipeline

            # Store camera in DB
            try:
                session = db.get_session()
                repo = Repository(session)
                existing = repo.get_camera(camera_info.camera_id)
                if not existing:
                    # Mock locations for the map view based on camera ID
                    lat, lng = 28.6139, 77.2090  # Default to New Delhi coordinates
                    if camera_info.camera_id == "cam_north":
                        lat, lng = 28.6150, 77.2100
                    elif camera_info.camera_id == "cam_south":
                        lat, lng = 28.6120, 77.2080

                    repo.create_camera(
                        camera_id=camera_info.camera_id,
                        name=camera_info.name,
                        stream_url=camera_info.source,
                        camera_type=camera_info.camera_type,
                        latitude=lat,
                        longitude=lng,
                    )
                session.close()
            except Exception as e:
                logger.error(f"DB camera save error: {e}")

        logger.success(f"IBVAP Pipeline initialized with {len(self.camera_pipelines)} cameras")

    def start_all(self):
        """Start all camera pipelines."""
        for cam_id, pipeline in self.camera_pipelines.items():
            pipeline.start()

    def stop_all(self):
        """Stop all camera pipelines."""
        for cam_id, pipeline in self.camera_pipelines.items():
            pipeline.stop()

    def get_pipeline(self, camera_id: str) -> CameraPipeline | None:
        return self.camera_pipelines.get(camera_id)

    def get_all_stats(self) -> dict[str, dict]:
        return {cam_id: pipeline.get_stats() for cam_id, pipeline in self.camera_pipelines.items()}

    def _load_yaml(self, filename: str) -> dict:
        filepath = self.config_dir / filename
        try:
            with open(filepath) as f:
                return yaml.safe_load(f) or {}
        except FileNotFoundError:
            logger.warning(f"Config file not found: {filepath}")
            return {}
        except Exception as e:
            logger.error(f"Error loading {filepath}: {e}")
            return {}
