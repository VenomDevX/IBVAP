"""
IBVAP — ByteTrack Multi-Object Tracker
Integrates ByteTrack for persistent object tracking across frames.
"""

import uuid

import cv2
import numpy as np
from loguru import logger

try:
    import supervision as sv
except ImportError:
    sv = None
    logger.warning("supervision not installed — tracker will use basic mode")

from src.detection.detection_result import FrameDetections
from src.detection.detector import COCO_TARGET_CLASSES
from src.tracking.track import NIGHT_VISION_CATCHALL, Track


def _bbox_iou(a: tuple, b: tuple) -> float:
    """Intersection-over-union of two (x1, y1, x2, y2) boxes."""
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    area_a = max(0, ax2 - ax1) * max(0, ay2 - ay1)
    area_b = max(0, bx2 - bx1) * max(0, by2 - by1)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


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
        frame_rate: float = 30,
        session_id: str | None = None,
    ):
        self.max_age = max_age
        self.min_hits = min_hits
        self.iou_threshold = iou_threshold
        self.frame_rate = frame_rate
        self.session_id = session_id or str(uuid.uuid4())

        # ByteTrack tracker
        self._tracker = self._make_bytetrack(max_age, iou_threshold, min_hits, frame_rate)

        # Active tracks
        self._tracks: dict[int, Track] = {}
        self._next_id: int = 1

    @property
    def active_tracks(self) -> dict[int, Track]:
        """Get all currently active tracks."""
        return {tid: t for tid, t in self._tracks.items() if t.is_active}

    @property
    def all_tracks(self) -> dict[int, Track]:
        return self._tracks

    def update(self, frame_detections: FrameDetections) -> dict[int, Track]:
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
                    class_name = id2name.get(cls_id, COCO_TARGET_CLASSES.get(cls_id, f"class_{cls_id}"))

                    if tid in self._tracks:
                        # Update existing track
                        self._tracks[tid].update(bbox, conf, timestamp, class_name=class_name)
                    else:
                        # Create new track
                        track = Track(
                            track_id=tid,
                            object_type=class_name,
                            camera_id=camera_id,
                            session_id=self.session_id,
                            bbox=bbox,
                            confidence=conf,
                            first_seen=timestamp,
                            last_seen=timestamp,
                        )
                        track.update(bbox, conf, timestamp)
                        self._tracks[tid] = track

            # --- Fallback: reconcile tracks ByteTrack went quiet on ---
            # sv.ByteTrack (deprecated, removed in supervision 0.31) has been
            # observed to drop an already-confirmed track from its per-frame
            # output even though the same object is still being detected: it
            # reports the tracker_id on the activation frame, then omits it on
            # many subsequent frames despite an unchanged, high-confidence,
            # overlapping detection. Confirmed on both a static synthetic clip
            # and real moving traffic footage - not specific to either.
            #
            # Silently, this freezes `last_seen`, which freezes `duration`,
            # which gates ANPR extraction, face re-identification and the
            # stage-2 fine classifier: those features "stop working" for a
            # track ByteTrack has gone quiet on, even though the object is
            # still on screen.
            #
            # For each raw input detection not claimed by ByteTrack's own
            # output this frame, look for an EXISTING active track of the same
            # class with a strongly overlapping bbox and refresh it directly.
            # This never creates a new track - ByteTrack alone still owns
            # activation / min_hits - so it cannot produce a track ByteTrack
            # itself would not have produced; it only keeps an
            # already-confirmed track fresh when ByteTrack goes quiet on it.
            quiet = [(tid, t) for tid, t in self._tracks.items() if tid not in active_ids and t.is_active]
            if quiet and len(xyxy):
                # The candidate tracks are the same for every detection, so
                # score all pairs in one numpy IoU matrix (same formula as
                # _bbox_iou) instead of a Python loop over every track per
                # detection — that was O(detections x tracks) per frame.
                det = xyxy.astype(int).astype(float)
                trk = np.array([t.bbox for _, t in quiet], dtype=float)
                ix1 = np.maximum(det[:, None, 0], trk[None, :, 0])
                iy1 = np.maximum(det[:, None, 1], trk[None, :, 1])
                ix2 = np.minimum(det[:, None, 2], trk[None, :, 2])
                iy2 = np.minimum(det[:, None, 3], trk[None, :, 3])
                inter = np.clip(ix2 - ix1, 0, None) * np.clip(iy2 - iy1, 0, None)
                area_d = np.clip(det[:, 2] - det[:, 0], 0, None) * np.clip(det[:, 3] - det[:, 1], 0, None)
                area_t = np.clip(trk[:, 2] - trk[:, 0], 0, None) * np.clip(trk[:, 3] - trk[:, 1], 0, None)
                union = area_d[:, None] + area_t[None, :] - inter
                ious = np.divide(inter, union, out=np.zeros_like(inter), where=(inter > 0) & (union > 0))
                for j in range(len(xyxy)):
                    overlapping = np.flatnonzero(ious[j] > self.iou_threshold)
                    if overlapping.size == 0:
                        continue
                    cid = int(class_id[j])
                    cls_name = id2name.get(cid, COCO_TARGET_CLASSES.get(cid, f"class_{cid}"))
                    best_col, best_iou = None, self.iou_threshold
                    for col in overlapping:
                        tid, track = quiet[col]
                        if tid in active_ids:
                            continue
                        # Normally require the same class as the track already
                        # has. Relaxed for night_vision_object tracks: that label
                        # is a detector catch-all, and a later frame's clearer
                        # car/truck/motorcycle read must reach Track.update() (and
                        # its class-upgrade vote) even though the class differs —
                        # the IoU check is still the real match gate.
                        if track.object_type != cls_name and track.object_type != NIGHT_VISION_CATCHALL:
                            continue
                        if ious[j, col] > best_iou:
                            best_iou, best_col = ious[j, col], col
                    if best_col is not None:
                        tid, track = quiet[best_col]
                        box = tuple(int(v) for v in xyxy[j])
                        track.update(box, float(confidence[j]), timestamp, class_name=cls_name)
                        active_ids.add(tid)

            # Mark tracks not in current frame
            for tid, track in self._tracks.items():
                if tid not in active_ids and track.is_active:
                    age = timestamp - track.last_seen
                    if age > self.max_age / self.frame_rate:
                        track.is_active = False
                        track.status = "LOST"

        except Exception as e:
            logger.error(f"Tracking error: {e}")

        self._age_tracks(timestamp)
        return self.active_tracks

    def _age_tracks(self, current_time: float):
        """Mark stale tracks inactive and evict long-dead ones (bounds memory)."""
        inactive_after = self.max_age / self.frame_rate
        evict_after = 10 * inactive_after
        dead = []
        for tid, track in self._tracks.items():
            age = current_time - track.last_seen
            if track.is_active and age > inactive_after:
                track.is_active = False
                track.status = "LOST"
            if not track.is_active and age > evict_after:
                track.status = "CLOSED"
                dead.append(tid)
        for tid in dead:
            del self._tracks[tid]

    def get_track(self, track_id: int) -> Track | None:
        """Get a specific track by ID."""
        return self._tracks.get(track_id)

    @staticmethod
    def _make_bytetrack(max_age, iou_threshold, min_hits=3, frame_rate=30):
        """Construct sv.ByteTrack, tolerating its removal/signature change in newer supervision."""
        if sv is None:
            return None
        try:
            return sv.ByteTrack(
                track_activation_threshold=0.25,
                lost_track_buffer=max_age,
                minimum_matching_threshold=iou_threshold,
                frame_rate=frame_rate,
                minimum_consecutive_frames=min_hits,
            )
        except (AttributeError, TypeError) as e:
            logger.error(f"sv.ByteTrack unavailable ({e}) - tracker running in basic mode")
            return None

    def reset(self, session_id: str | None = None):
        """Reset all tracking state."""
        for track in self._tracks.values():
            track.is_active = False
            track.status = "CLOSED"
        self._tracks.clear()
        self.session_id = session_id or str(uuid.uuid4())
        self._tracker = self._make_bytetrack(self.max_age, self.iou_threshold, self.min_hits, self.frame_rate)

    @staticmethod
    def draw_tracks(
        frame: np.ndarray, tracks: dict[int, Track], show_trajectory: bool = True, trail_length: int = 30
    ) -> np.ndarray:
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
            label = f"ID:{tid} {track.effective_label()}"
            (lw, lh), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
            cv2.rectangle(annotated, (x1, y1 - lh - 8), (x1 + lw, y1), color, -1)
            cv2.putText(annotated, label, (x1, y1 - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

            # Trajectory trail
            if show_trajectory and len(track.trajectory) > 1:
                recent = track.get_recent_trajectory(trail_length)
                pts = np.array([(p[0], p[1]) for p in recent], dtype=np.int32)
                # Older half thin, newer half thick: the same tapered trail in
                # two draw calls instead of one cv2.line per segment per track.
                half = len(pts) // 2
                if half >= 1:
                    cv2.polylines(annotated, [pts[: half + 1]], False, color, 1)
                cv2.polylines(annotated, [pts[half:]], False, color, 2)

            # Centroid dot
            cv2.circle(annotated, (cx, cy), 4, color, -1)

        return annotated
