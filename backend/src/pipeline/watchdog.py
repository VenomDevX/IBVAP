"""
IBVAP — Camera watchdog.

A camera can stop without anything noticing. An exception in the capture
thread (OpenCV running out of memory, for example) ends that thread, file
sources have no reconnect path, and the processing loop then waits forever on
a frame that never changes while the API still reports the camera online.

The watchdog checks every running camera on a fixed interval and restarts the
ones whose processing thread, capture thread or frame flow has stopped. Each
camera backs off exponentially between attempts so a broken source is not
restarted in a tight loop, and the backoff clears once the camera is healthy.
"""

from __future__ import annotations

import os
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from loguru import logger

from src.ingestion.video_source import CameraStatus

# States in which a live stream is already reconnecting inside its own loop.
_STREAM_RECOVERING = {CameraStatus.CONNECTING, CameraStatus.STOPPED, CameraStatus.ERROR}


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return default


@dataclass
class _CameraState:
    runtime_id: int
    failures: int = 0
    next_attempt: float = 0.0
    last_restart: float | None = None


class CameraWatchdog:
    """Restarts cameras whose capture or processing has died."""

    def __init__(
        self,
        pipeline: Any,
        *,
        interval: float = 10.0,
        stale_after: float = 30.0,
        startup_grace: float = 10.0,
        base_backoff: float = 15.0,
        max_backoff: float = 300.0,
        clock: Callable[[], float] = time.monotonic,
        wall_clock: Callable[[], float] = time.time,
    ):
        self.pipeline = pipeline
        self.interval = interval
        self.stale_after = stale_after
        self.startup_grace = startup_grace
        self.base_backoff = base_backoff
        self.max_backoff = max_backoff
        self._clock = clock
        self._wall_clock = wall_clock
        self._states: dict[str, _CameraState] = {}
        self._started_at: float | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @staticmethod
    def enabled_from_env() -> bool:
        return os.getenv("IBVAP_CAMERA_WATCHDOG", "true").strip().lower() not in {"0", "false", "no", "off"}

    @classmethod
    def from_env(cls, pipeline: Any) -> CameraWatchdog:
        return cls(
            pipeline,
            interval=_env_float("IBVAP_WATCHDOG_INTERVAL_S", 10.0),
            stale_after=_env_float("IBVAP_WATCHDOG_STALE_S", 30.0),
            max_backoff=_env_float("IBVAP_WATCHDOG_MAX_BACKOFF_S", 300.0),
        )

    # ------------------------------------------------------------------ lifecycle

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        # Cameras connect in the background after start_all(); give them the
        # same grace a freshly restarted camera gets.
        self._started_at = self._clock()
        self._thread = threading.Thread(target=self._run, name="ibvap-camera-watchdog", daemon=True)
        self._thread.start()
        logger.info(
            "Camera watchdog started (check every {:.0f}s, stale after {:.0f}s)", self.interval, self.stale_after
        )

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=self.interval + 10)
            self._thread = None

    def _run(self) -> None:
        while not self._stop.wait(self.interval):
            try:
                self.check_once()
            except Exception:
                logger.exception("Camera watchdog check failed")

    # ------------------------------------------------------------------ checks

    def _in_grace(self, state: _CameraState, now: float) -> bool:
        started = [t for t in (state.last_restart, self._started_at) if t is not None]
        return any(now - t < self.startup_grace for t in started)

    def diagnose(self, runtime: Any, in_grace: bool = False) -> str | None:
        """Return why a camera needs a restart, or None if it looks healthy."""
        thread = getattr(runtime, "_thread", None)
        if thread is None or not thread.is_alive():
            return "processing thread stopped"

        source = runtime.video_source
        if source.is_stream() and source.status in _STREAM_RECOVERING:
            return None  # the processing loop reconnects live streams itself
        if in_grace:
            return None  # still connecting after a (re)start

        if not source.is_capturing:
            return "capture thread stopped"
        last_frame = source.last_frame_at
        if last_frame is None:
            return "no frame received"
        age = self._wall_clock() - last_frame
        if age > self.stale_after:
            return f"no new frame for {age:.0f}s"
        return None

    def _backoff(self, failures: int) -> float:
        return min(self.base_backoff * 2 ** max(failures - 1, 0), self.max_backoff)

    def check_once(self) -> list[str]:
        """Check every camera once; return the ids restarted."""
        if not getattr(self.pipeline, "_started", True):
            return []

        now = self._clock()
        runtimes = dict(self.pipeline.camera_pipelines)
        for gone in set(self._states) - set(runtimes):
            del self._states[gone]

        restarted: list[str] = []
        for camera_id, runtime in runtimes.items():
            state = self._states.get(camera_id)
            if state is None:
                state = self._states[camera_id] = _CameraState(runtime_id=id(runtime))
            elif state.runtime_id != id(runtime):
                # Reconfigured through the API or replaced by a restart.
                state.runtime_id = id(runtime)
                if state.last_restart is None or now - state.last_restart >= self.startup_grace:
                    state.last_restart = now

            in_grace = self._in_grace(state, now)
            reason = self.diagnose(runtime, in_grace)

            if reason is None:
                if not in_grace and state.failures:
                    logger.info("Camera {} recovered after {} restart(s)", camera_id, state.failures)
                    state.failures = 0
                    state.next_attempt = 0.0
                continue

            if now < state.next_attempt:
                continue

            state.failures += 1
            state.last_restart = now
            delay = self._backoff(state.failures)
            state.next_attempt = now + delay
            logger.warning(
                "Camera {} unhealthy ({}); restarting, attempt {} (next retry in {:.0f}s if it fails)",
                camera_id,
                reason,
                state.failures,
                delay,
            )
            try:
                ok = self.pipeline.restart_camera(camera_id)
            except Exception as exc:
                logger.error("Camera {} restart failed: {!r}", camera_id, exc)
                continue
            if ok:
                restarted.append(camera_id)
                current = self.pipeline.camera_pipelines.get(camera_id)
                if current is not None:
                    state.runtime_id = id(current)
            else:
                logger.error("Camera {} restart was refused (camera no longer configured)", camera_id)
        return restarted
