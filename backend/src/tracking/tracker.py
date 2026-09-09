"""
IBVAP — ByteTrack Multi-Object Tracker
Integrates ByteTrack for persistent object tracking across frames.
"""

from typing import Dict, Optional

import numpy as np
import cv2
from loguru import logger

try:
    import supervision as sv
except ImportError:
    sv = None
    logger.warning("supervision not installed — tracker will use basic mode")

from src.detection.detection_result import FrameDetections
from src.detection.detector import COCO_TARGET_CLASSES
from src.tracking.track import Track


class MultiObjectTracker:
    """
    ByteTrack-based multi-object tracker.
    Assigns persistent IDs to detected objects and maintains trajectories.
    """

    def __init__(
        self,
        max_age: int = 30,
        min_hits: int = 3,
        iou_threshold: float = 0.3,
    ):
        self.max_age = max_age
        self.min_hits = min_hits
        self.iou_threshold = iou_threshold

        # ByteTrack tracker
        self._tracker = self._make_bytetrack(max_age, iou_threshold)

        # Active tracks
        self._tracks: Dict[int, Track] = {}
        self._next_id: int = 1

    @property
    def active_tracks(self) -> Dict[int, Track]:
        """Get all currently active tracks."""
        return {tid: t for tid, t in self._tracks.items() if t.is_active}

    @property
    def all_tracks(self) -> Dict[int, Track]:
        return self._tracks

    def update(self, frame_detections: FrameDetections) -> Dict[int, Track]:
        """
        Update tracker with new frame detections.

        Args:
            frame_detections: Detection results for the current frame

        Returns:
            Dictionary of track_id -> Track for active tracks
        """
        timestamp = frame_detections.timestamp
        camera_id = frame_detections.camera_id

        # class id -> name for THIS frame, straight from the detector
        # (already normalised to the pipeline vocabulary). Falls back to COCO.
        id2name = {d.class_id: d.class_name for d in frame_detections.detections}

        if self._tracker is None or not frame_detections.detections:
            # Mark existing tracks as inactive if no detections
            self._age_tracks(timestamp)
            return self.active_tracks

        try:
            # Convert detections to supervision format
            det_array = frame_detections.to_numpy()  # [x1,y1,x2,y2,conf,cls]

            if len(det_array) == 0:
                self._age_tracks(timestamp)
                return self.active_tracks

            xyxy = det_array[:, :4]
            confidence = det_array[:, 4]
            class_id = det_array[:, 5].astype(int)

            sv_detections = sv.Detections(
                xyxy=xyxy,
                confidence=confidence,
                class_id=class_id,
            )

            # Run ByteTrack
            tracked = self._tracker.update_with_detections(sv_detections)

            # Update/create tracks
            active_ids = set()
            if tracked.tracker_id is not None:
                for i, tracker_id in enumerate(tracked.tracker_id):
                    tid = int(tracker_id)
                    active_ids.add(tid)

                    bbox = tuple(int(v) for v in tracked.xyxy[i])
                    conf = float(tracked.confidence[i])
                    cls_id = int(tracked.class_id[i])

                    # Map class ID to name — detector first, COCO fallback
                    class_name = id2name.get(
                        cls_id, COCO_TARGET_CLASSES.get(cls_id, f"class_{cls_id}")
                    )

                    if tid in self._tracks:
                        # Update existing track
                        self._tracks[tid].update(bbox, conf, timestamp)
                    else:
                        # Create new track
                        track = Track(
                            track_id=tid,
                            object_type=class_name,
                            camera_id=camera_id,
                            bbox=bbox,
                            confidence=conf,
                            first_seen=timestamp,
                            last_seen=timestamp,
                        )
                        track.update(bbox, conf, timestamp)
                        self._tracks[tid] = track

            # Mark tracks not in current frame
            for tid, track in self._tracks.items():
                if tid not in active_ids and track.is_active:
                    age = timestamp - track.last_seen
                    if age > self.max_age / 30.0:  # Convert frames to seconds
                        track.is_active = False

        except Exception as e:
            logger.error(f"Tracking error: {e}")

        self._age_tracks(timestamp)
        return self.active_tracks

    def _age_tracks(self, current_time: float):
        """Mark stale tracks inactive and evict long-dead ones (bounds memory)."""
        inactive_after = self.max_age / 30.0
        evict_after = 10 * inactive_after
        dead = []
        for tid, track in self._tracks.items():
            age = current_time - track.last_seen
            if track.is_active and age > inactive_after:
                track.is_active = False
            if not track.is_active and age > evict_after:
                dead.append(tid)
        for tid in dead:
            del self._tracks[tid]

    def get_track(self, track_id: int) -> Optional[Track]:
        """Get a specific track by ID."""
        return self._tracks.get(track_id)

    @staticmethod
    def _make_bytetrack(max_age, iou_threshold):
        """Construct sv.ByteTrack, tolerating its removal/signature change in newer supervision."""
        if sv is None:
            return None
        try:
            return sv.ByteTrack(
                track_activation_threshold=0.25,
                lost_track_buffer=max_age,
                minimum_matching_threshold=iou_threshold,
                frame_rate=30,
            )
        except (AttributeError, TypeError) as e:
            logger.error(f"sv.ByteTrack unavailable ({e}) - tracker running in basic mode")
            return None

    def reset(self):
        """Reset all tracking state."""
        self._tracks.clear()
        self._tracker = self._make_bytetrack(self.max_age, self.iou_threshold)

    @staticmethod
    def draw_tracks(frame: np.ndarray, tracks: Dict[int, Track],
                    show_trajectory: bool = True,
                    trail_length: int = 30) -> np.ndarray:
        """Draw tracking information on frame."""
        annotated = frame.copy()

        for tid, track in tracks.items():
            if not track.is_active:
                continue

            x1, y1, x2, y2 = track.bbox
            cx, cy = track.centroid

            # Color based on object type
            colors = {
                "person": (0, 255, 0),
                "car": (255, 165, 0),
                "motorcycle": (255, 255, 0),
                "bus": (0, 165, 255),
                "truck": (0, 0, 255),
            }
            color = colors.get(track.object_type, (128, 128, 128))

            # Bounding box
            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)

            # Track ID label
            label = f"ID:{tid} {track.object_type}"
            (lw, lh), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
            cv2.rectangle(annotated, (x1, y1 - lh - 8), (x1 + lw, y1), color, -1)
            cv2.putText(
                annotated, label, (x1, y1 - 4),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1
            )

            # Trajectory trail
            if show_trajectory and len(track.trajectory) > 1:
                recent = track.get_recent_trajectory(trail_length)
                pts = [(p[0], p[1]) for p in recent]
                for i in range(1, len(pts)):
                    thickness = max(1, int(2 * i / len(pts)))
                    cv2.line(annotated, pts[i - 1], pts[i], color, thickness)

            # Centroid dot
            cv2.circle(annotated, (cx, cy), 4, color, -1)

        return annotated
