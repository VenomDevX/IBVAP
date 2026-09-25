"""Central, failure-isolated health registry for pipeline models/services."""

import threading
import time
from dataclasses import asdict, dataclass


@dataclass
class ModelHealth:
    name: str
    state: str = "DISABLED"
    device: str = "n/a"
    load_time_ms: float | None = None
    identifier: str | None = None
    error: str | None = None


class ModelRegistry:
    def __init__(self):
        self._items: dict[str, ModelHealth] = {}
        self._started: dict[str, float] = {}
        self._lock = threading.RLock()

    def loading(self, name: str, identifier: str | None = None) -> None:
        with self._lock:
            self._started[name] = time.perf_counter()
            self._items[name] = ModelHealth(name, "LOADING", identifier=identifier)

    def ready(self, name: str, device: str = "cpu", identifier: str | None = None) -> None:
        with self._lock:
            started = self._started.pop(name, None)
            elapsed = (time.perf_counter() - started) * 1000 if started is not None else None
            self._items[name] = ModelHealth(name, "READY", device, round(elapsed, 1) if elapsed else None, identifier)

    def failed(self, name: str, error: object, identifier: str | None = None) -> None:
        with self._lock:
            started = self._started.pop(name, None)
            elapsed = (time.perf_counter() - started) * 1000 if started is not None else None
            safe_error = f"{type(error).__name__}: {str(error)[:160]}"
            self._items[name] = ModelHealth(
                name, "FAILED", "n/a", round(elapsed, 1) if elapsed else None, identifier, safe_error
            )

    def disabled(self, name: str, identifier: str | None = None, reason: str | None = None) -> None:
        with self._lock:
            self._items[name] = ModelHealth(name, "DISABLED", identifier=identifier, error=reason)

    def snapshot(self) -> list[dict]:
        with self._lock:
            return [asdict(self._items[name]) for name in sorted(self._items)]
