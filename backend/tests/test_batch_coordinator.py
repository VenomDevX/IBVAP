"""BatchDetectionCoordinator: routing, fallback and the stale-result race."""

import threading

import numpy as np

from src.detection.batch_coordinator import BatchDetectionCoordinator
from src.detection.detection_result import FrameDetections


class FakeDetector:
    """detect_batch returns each frame's first pixel value as a marker."""

    def __init__(self, batch_gate=None, fail=False):
        self.batch_gate = batch_gate
        self.fail = fail
        self.direct_calls = 0

    def detect_batch(self, frames, camera_ids=None):
        if self.batch_gate is not None:
            self.batch_gate.wait(5)
        if self.fail:
            raise RuntimeError("boom")
        return [[("batch", int(f[0, 0, 0]))] for f in frames]

    def detect(self, frame, frame_id=0, camera_id=""):
        self.direct_calls += 1
        return FrameDetections(
            frame_id=frame_id, camera_id=camera_id, timestamp=0.0, detections=[("direct", int(frame[0, 0, 0]))]
        )


def _frame(marker: int) -> np.ndarray:
    return np.full((4, 4, 3), marker, np.uint8)


def test_results_are_routed_to_their_own_camera():
    det = FakeDetector()
    coord = BatchDetectionCoordinator(det, tick_interval_s=0.005)
    try:
        out = {}
        for cam in ("a", "b", "c"):
            coord.register_camera(cam)

        def run(cam, marker):
            out[cam] = coord.submit(cam, _frame(marker), frame_id=marker)

        threads = [threading.Thread(target=run, args=(c, m)) for c, m in (("a", 1), ("b", 2), ("c", 3))]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert {c: fd.detections for c, fd in out.items()} == {
            "a": [("batch", 1)],
            "b": [("batch", 2)],
            "c": [("batch", 3)],
        }
        assert det.direct_calls == 0
    finally:
        coord.stop()


def test_late_batch_result_is_never_given_to_the_next_frame():
    gate = threading.Event()
    det = FakeDetector(batch_gate=gate)
    coord = BatchDetectionCoordinator(det, tick_interval_s=0.005, submit_timeout_s=0.1)
    try:
        coord.register_camera("a")
        # Frame 1 times out while its batch is stuck on the gate -> direct fallback.
        first = coord.submit("a", _frame(1), frame_id=1)
        assert first.detections == [("direct", 1)]

        # Release the stuck batch while frame 2 is waiting; its late result
        # (marker 1) must be ignored, and frame 2 must only ever see marker 2.
        second_out = {}
        t = threading.Thread(target=lambda: second_out.update(fd=coord.submit("a", _frame(2), frame_id=2)))
        t.start()
        gate.set()
        t.join(5)
        assert second_out["fd"].detections in ([("batch", 2)], [("direct", 2)])
    finally:
        gate.set()
        coord.stop()


def test_failed_batch_falls_back_instead_of_returning_empty():
    det = FakeDetector(fail=True)
    coord = BatchDetectionCoordinator(det, tick_interval_s=0.005)
    try:
        coord.register_camera("a")
        fd = coord.submit("a", _frame(7), frame_id=7)
        assert fd.detections == [("direct", 7)]
        assert det.direct_calls == 1
    finally:
        coord.stop()


def test_unregistered_camera_runs_directly():
    det = FakeDetector()
    coord = BatchDetectionCoordinator(det, tick_interval_s=0.005)
    try:
        fd = coord.submit("ghost", _frame(5), frame_id=5)
        assert fd.detections == [("direct", 5)]
    finally:
        coord.stop()
