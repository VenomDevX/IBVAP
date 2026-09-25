"""
IBVAP — Background worker for slow per-track enrichment.

ANPR OCR, face recognition, and the Stage-2 fine classifier are each gated
by their own recheck timer, but were previously invoked SYNCHRONOUSLY inside
the same per-camera loop that does GPU detection + tracking + frame
annotation. Whenever several tracks' recheck timers landed on the same
frame, that frame's processing time spiked, and the MJPEG stream re-served
a stale cached JPEG during the stall — a visible freeze-then-jump.

EnrichmentWorker runs those calls on a small shared thread pool instead, so
frame -> annotate -> publish stays fast and consistent. A recheck landing
one cycle "late" is invisible to an operator; a frozen video frame is not.
"""

import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from loguru import logger


class EnrichmentWorker:
    """At most one in-flight background call per (track, task) key.

    Callers submit a zero-arg callable that performs the slow work AND
    applies its result (e.g. assigning to track attributes) — the existing
    recheck-timer gating already limits how often this is attempted, so
    dropping a submission that overlaps a still-running one for the same
    key is safe and keeps the pool from backing up.
    """

    def __init__(self, max_workers: int = 3, max_pending: int = 64):
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="enrich")
        self._inflight_lock = threading.Lock()
        self._inflight: set[tuple[str, str]] = set()
        # In-flight keys include queued ones, so this bounds the executor queue:
        # on a crowded scene we drop rechecks (the timer retries) instead of
        # piling up stale crops in memory.
        self._max_pending = max_pending
        self._closed = False
        self.dropped = 0

    def submit(self, track_key: str, task_type: str, fn: Callable[[], None]) -> bool:
        """Run fn() in the background unless (track_key, task_type) is
        already in flight. Returns True if the task was submitted."""
        key = (track_key, task_type)
        with self._inflight_lock:
            if self._closed or key in self._inflight:
                return False
            if len(self._inflight) >= self._max_pending:
                self.dropped += 1
                return False
            self._inflight.add(key)

        def _run() -> None:
            try:
                fn()
            except Exception as exc:
                logger.error(
                    "Enrichment task failed track={} task={} error={}",
                    track_key,
                    task_type,
                    type(exc).__name__,
                )
            finally:
                with self._inflight_lock:
                    self._inflight.discard(key)

        try:
            self._pool.submit(_run)
        except RuntimeError:  # pool shut down between the check and the submit
            with self._inflight_lock:
                self._inflight.discard(key)
            return False
        return True

    def shutdown(self) -> None:
        with self._inflight_lock:
            self._closed = True
        self._pool.shutdown(wait=False, cancel_futures=True)
