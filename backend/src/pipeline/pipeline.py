"""
IBVAP — Video Processing Pipeline
Main orchestrator: Ingest → Detect → Track → Spatial → Temporal → Behavior → Fusion → Risk → Alert → Store
"""

import os
import threading
import time
import uuid
from pathlib import Path

import numpy as np
import yaml
from loguru import logger

from src.alerts.alert_engine import AlertEngine
from src.alerts.evidence_clip import EvidenceClipBuffer
from src.anpr import ocr as plate_ocr
from src.anpr.plate_assign import assign_plates, split_plates
from src.behavior.behavior_engine import BehaviorEngine
from src.classification.fine_classifier import FineClassifier
from src.database.db import get_database
from src.database.repository import Repository
from src.detection.batch_coordinator import BatchDetectionCoordinator
from src.detection.detector import ObjectDetector
from src.face.face_recognizer import FaceRecognizer
from src.features.anpr import PlateConsensus, extract_plate
from src.features.best_frame import update_best_frame
from src.features.color_extractor import get_dominant_color
from src.fusion.context_fusion import ContextFusion
from src.fusion.event_state_machine import EventStateMachine, IncidentTransition
from src.ingestion.video_source import CameraInfo, CameraStatus, VideoSource
from src.model_registry import ModelRegistry
from src.paths import backend_path, output_dir, snapshots_dir
from src.paths import config_dir as default_config_dir
from src.pipeline.enrichment_worker import EnrichmentWorker
from src.risk.risk_engine import RiskEngine
from src.spatial.direction_analyzer import DirectionAnalyzer
from src.spatial.fence_detector import FenceDetector
from src.spatial.heatmap_tracker import HeatmapTracker
from src.spatial.zone_manager import Zone, ZoneManager
from src.temporal.loitering_detector import LoiteringDetector
from src.temporal.night_detector import NightDetector
from src.tracking.track import configure_type_upgrade
from src.tracking.track_manager import TrackManager
from src.tracking.tracker import MultiObjectTracker
from src.watchlist.service import get_watchlist, reload_watchlist

_LIST_PRIORITY = {"wanted": 3, "vip": 2, "authorized": 1}


def apply_watchlist_hit(track, hit) -> bool:
    """Attach a watchlist hit to a track; a stronger list is never downgraded.

    An unconfirmed (exact=False) hit is latched like any other, except that a
    later *exact* read of the same list may confirm it — otherwise a single
    confusable fold would stick to the track for its whole life.
    """
    if hit is None:
        return False
    current = track.watchlist
    if current:
        rank = _LIST_PRIORITY.get(current["list_type"], 0)
        new_rank = _LIST_PRIORITY.get(hit.list_type, 0)
        confirming = new_rank == rank and hit.exact and not current.get("exact", True)
        if rank >= new_rank and not confirming:
            return False
    track.watchlist = hit.to_dict()
    if hit.kind == "face":
        track.identity_label = hit.label
        track.identity_score = hit.score
        # An unconfirmed match must not brand the person as wanted.
        if hit.list_type == "wanted" and hit.exact:
            track.identity_status = "wanted"
        else:
            track.identity_status = "known"
    logger.warning(
        "Watchlist {} match camera={} track={} list={} label={} score={:.2f}",
        hit.kind,
        track.camera_id,
        track.track_uuid,
        hit.list_type,
        hit.label,
        hit.score,
    )
    return True


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
        face_recognizer: FaceRecognizer | None = None,
        fine_classifier: FineClassifier | None = None,
        thresholds: dict | None = None,
        batch_coordinator: BatchDetectionCoordinator | None = None,
        enrichment_worker: EnrichmentWorker | None = None,
    ):
        self.camera_info = camera_info
        thresholds = thresholds or {}
        tracking = thresholds.get("tracking", {})
        behavior = thresholds.get("behavior", {})
        event_cfg = thresholds.get("events", {})
        self.stream_session_id = str(uuid.uuid4())
        self.video_source = VideoSource(camera_info)
        self.detector = detector  # Shared detector across cameras
        # Optional: route detect() through a shared multi-camera batch
        # coordinator instead of calling the detector directly, so the GPU
        # sees one batched forward pass per tick across all cameras. Both
        # are optional so tests/callers can still construct a CameraPipeline
        # standalone (falls back to calling self.detector directly).
        self.batch_coordinator = batch_coordinator
        self.enrichment_worker = enrichment_worker
        if self.batch_coordinator is not None:
            self.batch_coordinator.register_camera(camera_info.camera_id)
        self.tracker = MultiObjectTracker(
            max_age=tracking.get("max_age", 30),
            min_hits=tracking.get("min_hits", 3),
            iou_threshold=tracking.get("iou_threshold", 0.3),
            frame_rate=camera_info.fps_limit or 30,
            session_id=self.stream_session_id,
        )
        self.track_manager = TrackManager(expiry_seconds=event_cfg.get("track_ttl_seconds", 10))
        self.heatmap_tracker = HeatmapTracker()
        self.zone_manager = zone_manager
        self.fence_detector = fence_detector
        self.direction_analyzer = DirectionAnalyzer(
            min_trajectory_points=behavior.get("direction_min_points", 5),
            stationary_threshold=behavior.get("stationary_speed_threshold", 5.0),
        )
        self.loitering_detector = LoiteringDetector(
            threshold_seconds=behavior.get("loitering_threshold_seconds", 30),
            min_movement_pixels=behavior.get("loitering_min_movement", 50),
            stationary_speed_threshold=behavior.get("stationary_speed_threshold", 5.0),
        )
        self.night_detector = NightDetector(
            night_start=behavior.get("night_start", "19:00"),
            night_end=behavior.get("night_end", "05:00"),
            brightness_threshold=behavior.get("low_light_brightness_threshold", 60),
        )
        self.behavior_engine = BehaviorEngine(
            night_movement_event_enabled=behavior.get("night_movement_event_enabled", False)
        )
        self.event_state_machine = EventStateMachine(
            confirmation_frames=event_cfg.get("temporal_confirmation_frames", 1),
            confirmation_window=event_cfg.get("temporal_confirmation_window", 1),
            exit_grace_seconds=event_cfg.get("exit_grace_seconds", 2),
            cooldown_seconds=event_cfg.get("event_cooldown_seconds", 30),
            update_interval_seconds=event_cfg.get("update_interval_seconds", 1),
        )
        fusion = thresholds.get("fusion", {})
        self.context_fusion = ContextFusion(
            fusion_cooldown=fusion.get("track_cooldown_seconds", 120),
            incident_cooldown=fusion.get("incident_cooldown_seconds", 60),
            max_events_per_minute=fusion.get("max_events_per_minute_per_camera", 20),
        )
        self.risk_engine = RiskEngine(risk_config)
        self.alert_engine = alert_engine
        self.face_recognizer = face_recognizer or FaceRecognizer(enabled=False)
        self._face_check_times: dict[str, float] = {}
        self._timers_pruned_at = 0.0
        self._anpr_check_times: dict[str, float] = {}
        self._profile_persist_times: dict[str, float] = {}
        self._runtime_persisted_at = 0.0
        anpr_cfg = thresholds.get("anpr", {})
        self.plate_consensus = PlateConsensus(
            min_observations=anpr_cfg.get("consensus_min_observations", 3),
            min_confidence=anpr_cfg.get("consensus_min_confidence", 0.55),
        )
        self._ANPR_RECHECK_S = float(anpr_cfg.get("recheck_seconds", 1.0))
        self._ANPR_STRICT_FORMAT = bool(anpr_cfg.get("strict_format", True))
        self._ANPR_REQUIRE_DETECTED_PLATE = bool(anpr_cfg.get("require_detected_plate", True))
        evidence_cfg = thresholds.get("evidence", {})
        self.evidence_buffer = (
            EvidenceClipBuffer(
                camera_info.camera_id,
                output_dir() / "clips",
                pre_seconds=evidence_cfg.get("pre_event_seconds", 3),
                post_seconds=evidence_cfg.get("post_event_seconds", 3),
                capture_fps=evidence_cfg.get("capture_fps", 5),
                max_width=evidence_cfg.get("max_width", 960),
                jpeg_quality=evidence_cfg.get("jpeg_quality", 65),
                on_complete=self._clip_completed,
                max_clips_per_hour=evidence_cfg.get("max_clips_per_hour", 60),
                max_storage_mb=evidence_cfg.get("max_clip_storage_mb", 4096),
                min_free_mb=evidence_cfg.get("min_free_storage_mb", 1024),
            )
            if evidence_cfg.get("clips_enabled", True)
            else None
        )
        self.fine_classifier = fine_classifier or FineClassifier(enabled=False)
        self._fine_check_times: dict[str, float] = {}
        self._best_frame_check_times: dict[str, float] = {}
        self._FACE_RECHECK_S = 0.8  # Check faces more frequently (was 2.0)
        self._FINE_RECHECK_S = 2.0
        self._persist_events = os.getenv("IBVAP_PERSIST_EVENTS", "true").strip().lower() not in {
            "0",
            "false",
            "no",
            "off",
        }

        self._running = False
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._latest_frame: np.ndarray | None = None
        self._latest_annotated: np.ndarray | None = None
        self._frame_lock = threading.Lock()
        self._stats = {
            "frames_processed": 0,
            "frames_dropped_for_analysis": 0,
            "detections": 0,
            "active_tracks": 0,
            "events_generated": 0,
            "alerts_generated": 0,
            "face_checks": 0,
            "face_embeddings": 0,
            "fps": 0.0,
        }

    def start(self):
        """Start the processing pipeline in a background thread."""
        if self._running:
            return

        self._stop_event.clear()
        if self.batch_coordinator is not None:
            # stop() unregisters the camera; without this a restarted camera
            # silently falls back to slow single-frame detect() calls.
            self.batch_coordinator.register_camera(self.camera_info.camera_id)
        self._register_stream_session()
        self._running = True
        self._thread = threading.Thread(target=self._process_loop, daemon=True)
        self._thread.start()
        logger.info(f"Pipeline started for {self.camera_info.camera_id}")

    def stop(self):
        """Stop the processing pipeline."""
        self.request_stop()
        if self._thread:
            self._thread.join(timeout=5)
        for transition in self.event_state_machine.close_all():
            try:
                self._persist_transition(transition, frame=None)
            except Exception as exc:
                logger.error(
                    "Incident close persistence failed event_id={} error={}",
                    transition.event.event_id,
                    type(exc).__name__,
                )
        self.video_source.release()
        self._persist_camera_runtime("offline", force=True)
        self._close_stream_session()
        if self.batch_coordinator is not None:
            self.batch_coordinator.unregister_camera(self.camera_info.camera_id)
        logger.info(f"Pipeline stopped for {self.camera_info.camera_id}")

    def request_stop(self) -> None:
        """Signal this pipeline to stop without waiting for its worker thread."""
        self._running = False
        self._stop_event.set()

    def _process_loop(self):
        """Main processing loop."""
        if not self.video_source.connect() and not self._recover_source():
            self._running = False
            return
        last_frame_id = -1
        while self._running:
            try:
                start_time = time.time()

                # 1. Read frame
                ret, frame = self.video_source.read_frame()
                if not ret or frame is None:
                    if not self.video_source.is_stream():
                        # The capture reader thread loops file sources
                        # automatically.  A momentary None means it is
                        # resetting to frame 0 — wait briefly and retry
                        # instead of killing the pipeline.
                        self._stop_event.wait(0.05)
                        continue
                    # Stream error — try reconnect
                    if not self._recover_source():
                        self._running = False
                        break
                    continue

                frame_id = self.video_source.frame_id
                if frame_id == last_frame_id:
                    self._stop_event.wait(0.005)
                    continue
                if last_frame_id >= 0 and frame_id > last_frame_id + 1:
                    self._stats["frames_dropped_for_analysis"] += frame_id - last_frame_id - 1
                last_frame_id = frame_id
                camera_id = self.camera_info.camera_id

                # Store raw frame
                with self._frame_lock:
                    self._latest_frame = frame.copy()
                if self.evidence_buffer is not None:
                    self.evidence_buffer.add_frame(frame)
                self._persist_camera_runtime("online")

                # 2. Detect objects. Routed through the shared batch coordinator
                # when available so multiple cameras' frames are combined into
                # one GPU forward pass per tick instead of one call each.
                if self.batch_coordinator is not None:
                    detections = self.batch_coordinator.submit(camera_id, frame, frame_id)
                else:
                    detections = self.detector.detect(frame, frame_id, camera_id)
                self._stats["detections"] = len(detections.detections)

                # 3. Track objects. Plates are not objects of their own: they are
                # attached to the vehicle that carries them.
                detections, plate_detections = split_plates(detections)
                active_tracks = self.tracker.update(detections)
                assign_plates(active_tracks, plate_detections, frame)
                self.track_manager.update_tracks(self.tracker.all_tracks)
                self.heatmap_tracker.add_points(active_tracks)
                self._stats["active_tracks"] = len(active_tracks)
                # Brightness is a frame property. Computing it once avoids a
                # full-frame colour conversion for every person/vehicle.
                night_context = self.night_detector.get_night_context(frame)

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
                            # Crop quality scoring (grayscale + Laplacian) for
                            # every track on every frame was ~5% of GIL time on
                            # busy cameras; 4 checks/s per track is plenty.
                            last_scored = self._best_frame_check_times.get(track.track_uuid, 0.0)
                            if detections.timestamp - last_scored >= 0.25:
                                self._best_frame_check_times[track.track_uuid] = detections.timestamp
                                improved = update_best_frame(
                                    track, crop, frame.shape, (x1, y1, x2, y2), detections.timestamp
                                )
                            else:
                                improved = False
                            vehicle = track.object_type in (
                                "car",
                                "truck",
                                "bus",
                                "motorcycle",
                                "vehicle",
                                "military_ground_vehicle",
                                "night_vision_object",
                            )
                            if improved and vehicle:
                                track.color = get_dominant_color(track.best_frame)
                            if vehicle and self._anpr_due(track):
                                last = self._anpr_check_times.get(track.track_uuid, 0.0)
                                if time.time() - last >= self._ANPR_RECHECK_S:
                                    self._anpr_check_times[track.track_uuid] = time.time()
                                    self._run_anpr_check(track)
                            if (
                                self.fine_classifier.active
                                and FineClassifier.is_military(track.object_type)
                                and track.fine_type == "unknown"
                            ):
                                # Stage 2: name the specific type (F16, not
                                # "aircraft"). Throttled like the face check -
                                # a track's airframe does not change, so one
                                # answer every few seconds is plenty, and the
                                # gate inside classify() keeps low-confidence
                                # guesses out of an operator's display.
                                last = self._fine_check_times.get(track.track_uuid, 0.0)
                                if time.time() - last >= self._FINE_RECHECK_S:
                                    self._fine_check_times[track.track_uuid] = time.time()
                                    self._run_fine_classify(track)
                            if (
                                track.object_type == "person"
                                and track.identity_status == "unknown"
                                and self.face_recognizer.active
                                and improved
                                and track.best_frame_score >= 0.25  # Lowered for CCTV angles
                            ):
                                last = self._face_check_times.get(track.track_uuid, 0.0)
                                if time.time() - last >= self._FACE_RECHECK_S:
                                    self._face_check_times[track.track_uuid] = time.time()
                                    self._stats["face_checks"] += 1
                                    self._run_face_identify(track)

                    self._process_track(track, frame, night_context)

                self._persist_track_profiles(active_tracks.values())

                active_uuids = {track.track_uuid for track in active_tracks.values()}
                self._prune_track_timers(active_uuids)
                for transition in self.event_state_machine.expire_inactive(active_uuids):
                    self._persist_transition(transition, frame=None)

                # Annotate frame
                annotated = frame.copy()
                # Draw zones
                camera_zones = self.zone_manager.get_camera_zones(camera_id)
                if camera_zones:
                    annotated = ZoneManager.draw_zones(annotated, camera_zones)
                # Draw fences
                fences = self.fence_detector.camera_fences(camera_id)
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

    def _anpr_due(self, track) -> bool:
        """Only OCR a plate the detector found (unless configured to guess)."""
        if track.license_plate != "Unknown":
            return False
        if track.plate_crop is not None:
            return True
        return not self._ANPR_REQUIRE_DETECTED_PLATE and track.best_frame_score >= 0.35

    def _run_anpr_check(self, track) -> None:
        """ANPR OCR is slow (easyocr/paddleocr/tesseract cascade). Run it off
        the frame-production thread so a plate read can never stall video."""
        located = track.plate_crop is not None
        crop = track.plate_crop if located else track.best_frame

        def _work() -> None:
            plate = extract_plate(crop, strict_format=self._ANPR_STRICT_FORMAT, plate_located=located)
            if plate is not None and plate["text"] != "Unknown" and plate["confidence"] > 0:
                text, confidence = self.plate_consensus.add(track, plate["text"], plate["confidence"])
                if text != "UNKNOWN":
                    changed = track.license_plate != text
                    track.license_plate = text
                    track.plate_confidence = confidence
                    apply_watchlist_hit(track, get_watchlist().match_plate(text))
                    if changed:
                        self._persist_recognition("anpr", track, text, confidence)

        if self.enrichment_worker is not None:
            self.enrichment_worker.submit(track.track_uuid, "anpr", _work)
        else:
            _work()

    def _run_fine_classify(self, track) -> None:
        """Stage-2 classifier (GPU model call) run off the frame thread."""
        crop = track.best_frame

        def _work() -> None:
            fine = self.fine_classifier.classify(crop)
            if fine:
                track.fine_type = fine["type"]
                track.fine_confidence = fine["confidence"]

        if self.enrichment_worker is not None:
            self.enrichment_worker.submit(track.track_uuid, "fine_classify", _work)
        else:
            _work()

    def _run_face_identify(self, track) -> None:
        """Face embedding + gallery match (GPU model call) run off the frame thread."""
        crop = track.best_frame

        def _work() -> None:
            face = self.face_recognizer.best_face(crop)
            if face is None:
                return
            self._stats["face_embeddings"] += 1
            hit = get_watchlist().match_face(face.get("embedding"))
            if apply_watchlist_hit(track, hit):
                self._persist_recognition("face", track, hit.label, hit.score)
                return
            match = self.face_recognizer.match(face)
            if match and match["status"] != "unknown":
                track.identity_label = match["identity"]
                track.identity_score = match["similarity"]
                track.identity_status = match["status"]
                self._persist_recognition("face", track, match["identity"], match["similarity"])

        if self.enrichment_worker is not None:
            self.enrichment_worker.submit(track.track_uuid, "face_identify", _work)
        else:
            _work()

    def _prune_track_timers(self, active_uuids: set[str]) -> None:
        """Drop per-track throttle state for tracks that are gone (long sessions
        on busy roads otherwise accumulate one entry per track ever seen)."""
        now = time.time()
        if now - self._timers_pruned_at < 30.0:
            return
        self._timers_pruned_at = now
        for timers in (
            self._face_check_times,
            self._anpr_check_times,
            self._fine_check_times,
            self._best_frame_check_times,
            self._profile_persist_times,
        ):
            for key in [k for k in timers if k not in active_uuids]:
                del timers[key]

    def _persist_recognition(self, kind: str, track, label: str, score: float) -> None:
        """Record a plate read / face match so it is searchable after the track ends."""
        if not self._persist_events:
            return
        try:
            with get_database().get_session() as session:
                repo = Repository(session)
                if kind == "anpr":
                    repo.create_anpr_result(track.track_id, self.camera_info.camera_id, label, float(score))
                else:
                    repo.create_identity_result(track.track_id, self.camera_info.camera_id, label, float(score))
        except Exception as exc:
            logger.warning(
                "Could not persist {} result camera={} error={}",
                kind,
                self.camera_info.camera_id,
                type(exc).__name__,
            )

    def _recover_source(self) -> bool:
        if not self.video_source.is_stream():
            return False
        while self._running and not self._stop_event.is_set():
            if self.video_source.reconnect(self._stop_event):
                self._begin_stream_session()
                return True
            if self.video_source._reconnect_count >= self.video_source.max_reconnect_attempts:
                self.video_source._status = CameraStatus.OFFLINE
                self._persist_camera_runtime("offline", force=True)
                return False
        return False

    def _begin_stream_session(self) -> None:
        """Close old identities and start a collision-free tracker epoch."""
        for transition in self.event_state_machine.close_all():
            try:
                self._persist_transition(transition, frame=None)
            except Exception as exc:
                logger.error(
                    "Incident close persistence failed event_id={} error={}",
                    transition.event.event_id,
                    type(exc).__name__,
                )
        self._close_stream_session()
        self.stream_session_id = str(uuid.uuid4())
        self.tracker.reset(self.stream_session_id)
        self._register_stream_session()
        self.loitering_detector.reset()
        self._face_check_times.clear()
        self._fine_check_times.clear()
        self._anpr_check_times.clear()

    def _register_stream_session(self) -> None:
        try:
            with get_database().get_session() as session:
                Repository(session).start_camera_session(self.camera_info.camera_id, self.stream_session_id)
        except Exception as exc:
            logger.warning(
                "Could not persist camera session camera={} error={}", self.camera_info.camera_id, type(exc).__name__
            )

    def _close_stream_session(self) -> None:
        try:
            with get_database().get_session() as session:
                Repository(session).close_camera_session(self.stream_session_id)
        except Exception as exc:
            logger.warning(
                "Could not close camera session camera={} error={}", self.camera_info.camera_id, type(exc).__name__
            )

    def _persist_camera_runtime(self, status: str, force: bool = False) -> None:
        now = time.time()
        if not force and now - self._runtime_persisted_at < 2.0:
            return
        self._runtime_persisted_at = now
        try:
            with get_database().get_session() as session:
                Repository(session).update_camera_runtime(
                    self.camera_info.camera_id, status, self.video_source.last_frame_at
                )
        except Exception as exc:
            logger.warning(
                "Could not persist camera runtime camera={} error={}", self.camera_info.camera_id, type(exc).__name__
            )

    def _process_track(self, track, frame: np.ndarray, night_ctx: dict | None = None):
        """Process a single track through spatial/temporal/behavior/fusion/risk pipeline."""
        camera_id = track.camera_id
        cx, cy = track.centroid

        # 4. Spatial analysis
        object_type = track.object_type
        current_zone_ids = self.zone_manager.check_track_zones(camera_id, (cx, cy), object_type)
        track.current_zones = current_zone_ids
        in_restricted = self.zone_manager.is_in_restricted_zone(camera_id, cx, cy, object_type)

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
        spatial_context["approaching_fence"] = bool(approaching)

        # 5. Direction analysis
        direction = self.direction_analyzer.analyze_direction(track)
        track.movement_direction = direction
        toward_restricted = False
        for zone in self.zone_manager.get_camera_zones(camera_id):
            if zone.enabled and zone.zone_type == "restricted" and zone.applies_to(object_type):
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
        night_ctx = night_ctx or self.night_detector.get_night_context(frame)

        temporal_context = {
            "is_night": night_ctx.get("is_night", False),
            "is_night_time": night_ctx.get("is_night_time", False),
            "is_loitering": len(loiter_events) > 0 or track.is_loitering,
            "loiter_duration": max(
                (self.loitering_detector.get_zone_duration(track.track_uuid, zid) for zid in current_zone_ids),
                default=0,
            ),
            "loiter_zone": loiter_events[0].zone_id if loiter_events else "",
            "zone_session_id": next(
                (track.zone_session_ids[zid] for zid in current_zone_ids if zid in track.zone_session_ids),
                None,
            ),
            "brightness": night_ctx.get("brightness", 128),
        }

        # 7. Behavior analysis
        behavior_events = self.behavior_engine.analyze_track(
            track, spatial_context, temporal_context, direction_context, fence_context, apply_cooldown=False
        )

        if not behavior_events:
            track.risk_score = 0.0
            track.risk_level = "low"
            track.risk_factors = []
            for transition in self.event_state_machine.observe(track.track_uuid, []):
                self._persist_transition(transition, frame=None)
            return

        # 8. Context fusion
        identity_context = {}
        if track.color != "Unknown":
            identity_context["color"] = track.color
        if track.object_type == "person":
            identity_context["identity"] = track.identity_label
            identity_context["identity_status"] = (
                track.identity_status if self.face_recognizer.active else "not_checked"
            )
            identity_context["identity_score"] = track.identity_score
        if track.watchlist and track.watchlist["kind"] == "face":
            identity_context["watchlist"] = track.watchlist

        vehicle_context = {}
        if track.object_type in (
            "car",
            "truck",
            "bus",
            "motorcycle",
            "vehicle",
            "military_ground_vehicle",
            "night_vision_object",
        ):
            vehicle_context["plate"] = track.license_plate
            vehicle_context["plate_confidence"] = track.plate_confidence
            vehicle_context["plate_status"] = (
                "not_detected"
                if track.license_plate == "Unknown"
                else "low_confidence"
                if track.plate_confidence < 0.6
                else "read"
            )
        if track.watchlist and track.watchlist["kind"] == "plate":
            vehicle_context["watchlist"] = track.watchlist

        fused_event = self.context_fusion.fuse_events(
            track_id=track.track_id,
            track_uuid=track.track_uuid,
            camera_id=camera_id,
            object_type=track.object_type,
            behavior_events=behavior_events,
            spatial_context=spatial_context,
            temporal_context=temporal_context,
            identity_context=identity_context,
            vehicle_context=vehicle_context,
            track_duration=track.duration,
            raw_class=track.raw_class,
            suspected_type=track.suspected_type,
        )

        if fused_event is None:
            return

        # 9. Risk scoring
        fused_event = self.risk_engine.score_fused_event(fused_event)

        # Attach latest risk to the track for live dashboard
        track.risk_score = fused_event.risk_score
        track.risk_level = fused_event.risk_level
        track.risk_factors = fused_event.contributing_factors
        track.score_breakdown = fused_event.score_breakdown

        transitions = self.event_state_machine.observe(track.track_uuid, [fused_event])
        for transition in transitions:
            evidence_frame = track.best_frame if track.best_frame is not None else frame
            self._persist_transition(transition, evidence_frame if transition.action == "opened" else None)

    def _persist_track_profile(self, track) -> None:
        """Persist one profile; retained for focused callers/tests."""
        self._persist_track_profiles([track])

    def _persist_track_profiles(self, tracks) -> None:
        """Batch due track/profile writes into one transaction per frame."""
        if not self._persist_events:
            return
        now = time.time()
        # Every upsert serializes the track's whole trajectory (up to 500
        # points) to JSON; at 1s this was ~13% of GIL time on busy cameras.
        due = [track for track in tracks if now - self._profile_persist_times.get(track.track_uuid, 0.0) >= 5.0]
        if not due:
            return
        vehicle_types = {
            "car",
            "truck",
            "bus",
            "motorcycle",
            "vehicle",
            "military_ground_vehicle",
            "night_vision_object",
        }
        try:
            with get_database().get_session() as session:
                Repository(session).upsert_track_profiles(due, vehicle_types)
                session.commit()
            for track in due:
                self._profile_persist_times[track.track_uuid] = now
        except Exception as exc:
            logger.error(
                "Track profile batch persistence failed camera={} tracks={} error={}",
                self.camera_info.camera_id,
                len(due),
                type(exc).__name__,
            )

    def _persist_transition(self, transition: IncidentTransition, frame: np.ndarray | None) -> None:
        """Persist a lifecycle transition; only OPEN may create an alert/evidence."""
        fused_event = transition.event
        action = transition.action

        # Keep operational logs bounded. Full explanation remains on the event.
        if action in {"opened", "escalated"} and fused_event.risk_level in ("high", "critical"):
            logger.warning(
                "High-risk event camera={} track={} type={} score={:.0f}",
                fused_event.camera_id,
                fused_event.track_uuid,
                fused_event.event_type,
                fused_event.risk_score,
            )

        if not self._persist_events:
            alert = (
                self.alert_engine.generate_alert(fused_event, frame=None, publish=False) if action == "opened" else None
            )
            if action == "opened":
                self.context_fusion.mark_recorded(fused_event)
                self._stats["events_generated"] += 1
            if alert:
                self.alert_engine.publish_alert(alert)
                self._stats["alerts_generated"] += 1
            return

        # Serialize chain appends across camera workers; publish only committed alerts.
        with self.alert_engine.persistence_lock:
            alert = self.alert_engine.generate_alert(fused_event, frame, publish=False) if action == "opened" else None
            if alert and alert.snapshot_path:
                fused_event.evidence_path = alert.snapshot_path
                fused_event.evidence_hash = alert.snapshot_hash
            with get_database().get_session() as session:
                repo = Repository(session)
                try:
                    if action == "opened":
                        repo.create_event(fused_event.to_dict(), commit=False)
                    else:
                        repo.update_event_lifecycle(fused_event.to_dict(), commit=False)
                    if action == "escalated":
                        repo.update_alert_from_event(fused_event.to_dict(), commit=False)
                    if alert:
                        repo.create_alert(alert.to_dict(), commit=False)
                    if action == "opened" and fused_event.evidence_path:
                        repo.create_event_evidence(
                            fused_event.event_id,
                            "best_snapshot",
                            snapshot_path=fused_event.evidence_path,
                            commit=False,
                        )
                    session.commit()
                except Exception:
                    session.rollback()
                    if action == "opened":
                        self.event_state_machine.rollback_open(fused_event.event_id)
                        if alert and alert.snapshot_path and os.path.isfile(alert.snapshot_path):
                            try:
                                os.remove(alert.snapshot_path)
                            except OSError:
                                pass
                    raise
                if action == "opened":
                    self.context_fusion.mark_recorded(fused_event)
                    self._stats["events_generated"] += 1
                if alert:
                    self.alert_engine.publish_alert(alert)
                    self._stats["alerts_generated"] += 1
                # Clip only incidents that became alerts: alerts are already
                # risk-gated and rate-limited, events are not.
                if alert and self.evidence_buffer is not None:
                    self.evidence_buffer.trigger(fused_event.event_id)

    def _clip_completed(self, event_id: str, clip_path: str) -> None:
        with get_database().get_session() as session:
            Repository(session).create_event_evidence(event_id, "pre_post_clip", clip_path=clip_path)

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
            "capture_fps": round(self.video_source.fps, 1),
            "capture_frame_id": self.video_source.frame_id,
            "inference_ms": round(self.detector.get_average_inference_time(), 1),
            "detector_queue_ms": round(self.detector.get_average_queue_wait_time(), 1),
            "detector_service_ms": round(self.detector.get_average_service_time(), 1),
            "detector_capacity_fps": round(self.detector.get_fps(), 1),
            "camera_status": self.video_source.status.value,
            "camera_id": self.camera_info.camera_id,
        }


class IBVAPPipeline:
    """
    Master pipeline managing multiple camera pipelines.
    Entry point for the IBVAP processing system.
    """

    def __init__(self, config_dir: str | None = None):
        self.config_dir = Path(config_dir).resolve() if config_dir else default_config_dir()
        self.camera_pipelines: dict[str, CameraPipeline] = {}
        self.detector: ObjectDetector | None = None
        self.batch_coordinator: BatchDetectionCoordinator | None = None
        self.enrichment_worker: EnrichmentWorker | None = None
        self.zone_manager = ZoneManager()
        self.fence_detector = FenceDetector()
        self.alert_engine = AlertEngine()
        self.face_recognizer: FaceRecognizer | None = None
        self.fine_classifier: FineClassifier | None = None
        self._risk_config = {}
        self._thresholds_config = {}
        self._started = False
        self.model_registry = ModelRegistry()

    def initialize(self):
        """Load configs and initialize all components."""
        logger.info("Initializing IBVAP Pipeline...")

        # Load configurations
        cameras_config = self._load_yaml("cameras.yaml")
        zones_config = self._load_yaml("zones.yaml")
        thresholds_config = self._load_yaml("thresholds.yaml")
        self._thresholds_config = thresholds_config
        self._risk_config = self._load_yaml("risk_weights.yaml")
        tracking_cfg = thresholds_config.get("tracking", {})
        configure_type_upgrade(
            tracking_cfg.get("type_upgrade_confidence", 0.45),
            tracking_cfg.get("type_upgrade_margin", 0.10),
        )

        # Initialize detector (shared across cameras)
        det_cfg = thresholds_config.get("detection", {})
        weights_path = det_cfg.get("weights_path") or ""
        if weights_path:
            weights_path = str(backend_path(weights_path))
        use_custom = bool(weights_path) and os.path.exists(weights_path)
        if weights_path and not use_custom:
            logger.warning(f"detection.weights_path set but not found ({weights_path}) - using stock model")
        detector_identifier = weights_path if use_custom else det_cfg.get("model_variant", "yolov8n") + ".pt"
        fallback_path = det_cfg.get("fallback_weights_path") if use_custom else None
        if fallback_path:
            fallback_path = str(backend_path(fallback_path))
            if not os.path.exists(fallback_path):
                logger.warning(f"detection.fallback_weights_path not found ({fallback_path}) - fallback disabled")
                fallback_path = None
        self.model_registry.loading("object_detector", os.path.basename(detector_identifier))
        engine_path = det_cfg.get("engine_path") or ""
        if engine_path:
            engine_path = str(backend_path(engine_path))
        self.detector = ObjectDetector(
            model_path=detector_identifier,
            confidence_threshold=det_cfg.get("confidence_threshold", 0.40),
            nms_threshold=det_cfg.get("nms_threshold", 0.45),
            target_classes=det_cfg.get("target_classes") or [0, 2, 3, 5, 7],
            device=det_cfg.get("device", "auto"),
            imgsz=det_cfg.get("imgsz", 640),
            detect_all=use_custom,  # custom coarse model: emit all its classes
            class_thresholds=det_cfg.get("class_thresholds", {}),
            half_precision=det_cfg.get("half_precision", True),
            fallback_model_path=fallback_path,
            engine_path=engine_path or None,
            agnostic_nms=det_cfg.get("agnostic_nms", False),
            augment=det_cfg.get("augment", False),
            max_det=det_cfg.get("max_det", 300),
        )
        if self.detector._model is None:
            self.model_registry.failed(
                "object_detector", RuntimeError("model unavailable"), os.path.basename(detector_identifier)
            )
        else:
            self.model_registry.ready("object_detector", self.detector._device, os.path.basename(detector_identifier))

        # Batches per-camera frames into one GPU forward pass per tick
        # instead of each CameraPipeline calling detect() one frame at a
        # time (see plan: "full GPU utilization") — but ONLY when the loaded
        # model can actually accept a multi-frame batch. A TensorRT engine
        # compiled with a fixed batch dimension (this deployment's
        # models/ibvap_coarse.engine is fixed at 1) rejects anything larger,
        # so detect_batch() falls back to calling the model once per frame
        # ANYWAY — except now every camera also pays the coordinator's
        # submit/tick/timeout overhead on top for zero benefit. Measured
        # impact of enabling it unconditionally: per-camera FPS collapsed
        # from ~10-15 to ~0.6-0.9 (every submission timed out after the
        # full submit_timeout_s before falling back). Probe once at
        # startup with a real 2-frame batch and only wire the coordinator
        # in if the model accepts it.
        if self.detector._model is not None:
            dummy = np.zeros((64, 64, 3), dtype=np.uint8)
            self.detector.detect_batch([dummy, dummy])
        if self.detector._model is not None and not self.detector._batch_unsupported_warned:
            self.batch_coordinator = BatchDetectionCoordinator(self.detector)
        else:
            if self.detector._model is not None:
                logger.info(
                    "Loaded model does not support multi-frame batching "
                    "(fixed batch size) — cameras will call detect() directly."
                )
            self.batch_coordinator = None
        # Runs ANPR OCR / face recognition / fine classification off the
        # frame-production thread so a slow recheck can't stall the video
        # stream (see plan: "smooth video without losing accuracy").
        self.enrichment_worker = EnrichmentWorker()

        # Initialize fences
        self.fence_detector.load_from_config(zones_config)

        # Initialize alert engine
        alert_cfg = thresholds_config.get("alerts", {})
        self.alert_engine = AlertEngine(
            cooldown_seconds=alert_cfg.get("cooldown_seconds", 60),
            max_alerts_per_minute=alert_cfg.get("max_alerts_per_minute", 10),
            min_risk_score=alert_cfg.get("min_alert_risk_score", 20),
            snapshots_dir=str(snapshots_dir()),
            max_snapshots_per_hour=alert_cfg.get("max_snapshots_per_hour_per_camera", 60),
            max_snapshot_storage_mb=alert_cfg.get("max_snapshot_storage_mb", 2048),
            min_free_storage_mb=alert_cfg.get("min_free_storage_mb", 1024),
        )

        # Face recognition (shared model, off by default — see thresholds.yaml)
        fc = thresholds_config.get("face", {})
        self.face_recognizer = FaceRecognizer(
            enabled=bool(fc.get("enabled", False)),
            gallery_path=str(backend_path(fc.get("gallery_path", "./models/face/gallery.json"))),
            similarity_threshold=fc.get("similarity_threshold", 0.45),
            uncertain_threshold=fc.get("uncertain_threshold", 0.35),
            min_face_confidence=fc.get("min_face_confidence", 0.6),
            device=fc.get("device", "auto"),
        )
        if not fc.get("enabled", False):
            self.model_registry.disabled("face_recognition", reason="disabled by configuration")
        elif self.face_recognizer.active:
            self.model_registry.ready("face_recognition", self.face_recognizer._detector.device, "insightface")
        else:
            self.model_registry.failed(
                "face_recognition", RuntimeError("dependency, weights, or gallery unavailable"), "insightface"
            )

        # Stage 2 fine-grained classifier (military crops only). On by default;
        # disables itself when the weights are absent - see thresholds.yaml.
        cc = thresholds_config.get("classifier", {})
        self.fine_classifier = FineClassifier(
            enabled=bool(cc.get("enabled", True)),
            weights=str(backend_path(cc.get("weights", "./models/classifier/ibvap_fine.pt"))),
            min_confidence=float(cc.get("min_confidence", 0.55)),
            device=cc.get("device"),
        )
        if not cc.get("enabled", True):
            self.model_registry.disabled("fine_classifier", reason="disabled by configuration")
        elif self.fine_classifier.active:
            self.model_registry.ready(
                "fine_classifier", str(self.fine_classifier._device), os.path.basename(cc.get("weights", ""))
            )
        else:
            self.model_registry.failed(
                "fine_classifier",
                RuntimeError("weights or architecture unavailable"),
                os.path.basename(cc.get("weights", "")),
            )

        self.model_registry.ready("tracker", "cpu", "ByteTrack")
        self.model_registry.ready("vehicle_attribute_service", "cpu", "deterministic-hsv-laplacian")
        import importlib.util

        if any(importlib.util.find_spec(name) is not None for name in ("easyocr", "paddleocr", "pytesseract")):
            self.model_registry.ready("ocr", "cpu", "local-adapter")
        else:
            self.model_registry.disabled("ocr", reason="no supported OCR engine installed")
        plate_path = backend_path("models/anpr/plate_detector.pt")
        if plate_path.exists():
            self.model_registry.ready("anpr_detector", self.detector._device, plate_path.name)
        else:
            self.model_registry.disabled("anpr_detector", reason="optional detector weights not installed")

        # Seed every configured camera, including disabled cameras, before zones
        # so foreign-key enforcement never depends on startup ordering.
        self._sync_cameras(cameras_config)

        # Import YAML zone defaults once; database rows, including soft
        # deletions, take precedence after their parent cameras exist.
        self._restore_zones(zones_config)

        if thresholds_config.get("anpr", {}).get("ocr_subprocess", True):
            plate_ocr.use_subprocess(True)
            # Loading PaddleOCR in the worker takes ~30 s; do it now, not on the first plate.
            threading.Thread(
                target=lambda: logger.info("ANPR OCR worker ready: {}", plate_ocr.engine_name()),
                name="ocr-warmup",
                daemon=True,
            ).start()

        watchlist = get_watchlist()
        watchlist.face_threshold = float(fc.get("watchlist_threshold", fc.get("similarity_threshold", 0.45)))
        try:
            reload_watchlist()
            logger.info("Watchlist loaded: {}", watchlist.size)
        except Exception as exc:
            logger.error("Watchlist load failed error={}", type(exc).__name__)

        # Start cameras from the database, not cameras.yaml: it holds the user's
        # enable/disable choices and cameras added in the UI.
        with get_database().get_session() as session:
            for camera in self._cameras_to_start(session):
                self.configure_camera(camera)

        logger.success(f"IBVAP Pipeline initialized with {len(self.camera_pipelines)} cameras")

    def _sync_cameras(self, cameras_config: dict) -> None:
        """cameras.yaml seeds and refreshes camera rows, except for fields a user
        changed (CameraModel.user_overrides) and cameras a user retired."""
        with get_database().get_session() as session:
            repo = Repository(session)
            for cam_cfg in cameras_config.get("cameras", []):
                values = {
                    "name": cam_cfg["name"],
                    "source": cam_cfg["source"],
                    "type": cam_cfg.get("type", "general"),
                    "location": cam_cfg.get("location", ""),
                    "latitude": cam_cfg.get("latitude"),
                    "longitude": cam_cfg.get("longitude"),
                    "enabled": cam_cfg.get("enabled", True),
                    "fps_limit": cam_cfg.get("fps", cam_cfg.get("fps_limit", 15)),
                    "resolution": cam_cfg.get("resolution"),
                }
                existing = repo.get_camera(cam_cfg["id"])
                if existing is None:
                    repo.create_camera(
                        camera_id=cam_cfg["id"],
                        name=values["name"],
                        stream_url=values["source"],
                        camera_type=values["type"],
                        location_label=values["location"],
                        latitude=values["latitude"],
                        longitude=values["longitude"],
                        enabled=values["enabled"],
                        fps_limit=values["fps_limit"],
                        resolution=values["resolution"],
                    )
                    continue
                if existing.status == "retired":
                    continue
                keep = set(existing.user_overrides or [])
                repo.update_camera(cam_cfg["id"], {k: v for k, v in values.items() if k not in keep})

    @staticmethod
    def _cameras_to_start(session) -> list:
        from src.database.models import CameraModel

        return (
            session.query(CameraModel)
            .filter(CameraModel.enabled.is_(True), CameraModel.status != "retired")
            .order_by(CameraModel.id)
            .all()
        )

    def start_all(self):
        """Start all camera pipelines."""
        self._started = True
        for cam_id, pipeline in self.camera_pipelines.items():
            pipeline.start()

    def _restore_zones(self, zones_config: dict):
        defaults = ZoneManager()
        defaults.load_from_config(zones_config)
        with get_database().get_session() as session:
            repo = Repository(session)
            existing = {z.zone_id for z in repo.get_zones(include_deleted=True)}
            for zone in defaults.get_all_zones():
                if zone["zone_id"] not in existing:
                    repo.create_zone(zone)
            self.zone_manager = ZoneManager()
            for row in repo.get_zones():
                default = defaults.get_zone(row.zone_id)
                if row.trigger_classes is None and default is not None and default.trigger_classes:
                    # Zones seeded before trigger_classes was persisted: backfill from YAML.
                    repo.update_zone(row.zone_id, {"trigger_classes": list(default.trigger_classes)})
                self.zone_manager.add_zone(
                    Zone(
                        zone_id=row.zone_id,
                        camera_id=row.camera_id,
                        name=row.name,
                        zone_type=row.zone_type,
                        points=[tuple(p) for p in row.points],
                        color=tuple(row.color),
                        enabled=row.enabled,
                        trigger_classes=list(row.trigger_classes or []),
                    )
                )

    def stop_all(self):
        """Stop all camera pipelines."""
        self._started = False
        # Signal every worker first so shutdown is bounded by one slow call,
        # rather than a separate five-second wait for every camera.
        for pipeline in self.camera_pipelines.values():
            pipeline.request_stop()
        for pipeline in self.camera_pipelines.values():
            pipeline.stop()
        if self.batch_coordinator is not None:
            self.batch_coordinator.stop()
        if self.enrichment_worker is not None:
            self.enrichment_worker.shutdown()
        plate_ocr.use_subprocess(False)

    def get_pipeline(self, camera_id: str) -> CameraPipeline | None:
        return self.camera_pipelines.get(camera_id)

    def configure_camera(self, camera) -> None:
        """Create or replace one runtime pipeline from a persisted camera row."""
        existing = self.camera_pipelines.pop(camera.camera_id, None)
        if existing:
            existing.stop()
        if not camera.enabled:
            return
        source = camera.stream_url
        if "://" not in source and not os.path.isabs(source):
            source = str((Path(__file__).resolve().parents[2] / source).resolve())
        info = CameraInfo(
            camera_id=camera.camera_id,
            name=camera.name,
            source=source,
            camera_type=camera.camera_type,
            enabled=camera.enabled,
            fps_limit=camera.fps_limit or 15,
            resolution=tuple(camera.resolution) if camera.resolution else None,
        )
        runtime = CameraPipeline(
            camera_info=info,
            detector=self.detector,
            zone_manager=self.zone_manager,
            fence_detector=self.fence_detector,
            risk_config=self._risk_config,
            alert_engine=self.alert_engine,
            face_recognizer=self.face_recognizer,
            fine_classifier=self.fine_classifier,
            thresholds=self._thresholds_config,
            batch_coordinator=self.batch_coordinator,
            enrichment_worker=self.enrichment_worker,
        )
        self.camera_pipelines[camera.camera_id] = runtime
        if self._started:
            runtime.start()

    def remove_camera(self, camera_id: str) -> None:
        runtime = self.camera_pipelines.pop(camera_id, None)
        if runtime:
            runtime.stop()

    def restart_camera(self, camera_id: str) -> bool:
        runtime = self.camera_pipelines.get(camera_id)
        if runtime is None:
            return False
        runtime.stop()
        runtime.start()
        return True

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
