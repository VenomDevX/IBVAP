"""Camera watchdog: restarts cameras whose capture or processing has died."""

from types import SimpleNamespace

from src.ingestion.video_source import CameraInfo, CameraStatus, VideoSource
from src.pipeline.watchdog import CameraWatchdog


class Clock:
    def __init__(self, start: float = 1000.0):
        self.now = start

    def __call__(self) -> float:
        return self.now


class FakeThread:
    def __init__(self, alive: bool = True):
        self.alive = alive

    def is_alive(self) -> bool:
        return self.alive


def make_runtime(clock: Clock, *, capturing=True, processing=True, frame_age=1.0, stream=False):
    source = SimpleNamespace(
        is_capturing=capturing,
        last_frame_at=clock.now - frame_age,
        status=CameraStatus.ONLINE,
        is_stream=lambda: stream,
    )
    return SimpleNamespace(video_source=source, _thread=FakeThread(processing), _running=processing)


class FakeMaster:
    """Stands in for IBVAPPipeline. A restart makes the camera healthy unless told otherwise."""

    def __init__(self, clock: Clock, runtimes: dict, heal_on_restart: bool = True):
        self.clock = clock
        self.camera_pipelines = runtimes
        self._started = True
        self.heal_on_restart = heal_on_restart
        self.restarts: list[str] = []

    def restart_camera(self, camera_id: str) -> bool:
        self.restarts.append(camera_id)
        if self.heal_on_restart:
            self.camera_pipelines[camera_id] = make_runtime(self.clock)
        return True


def watchdog_for(master, clock, **kwargs):
    options = dict(stale_after=30.0, startup_grace=10.0, base_backoff=15.0, max_backoff=120.0)
    options.update(kwargs)
    return CameraWatchdog(master, clock=clock, wall_clock=clock, **options)


def test_healthy_cameras_are_left_alone():
    clock = Clock()
    master = FakeMaster(clock, {"CAM_A": make_runtime(clock)})
    assert watchdog_for(master, clock).check_once() == []
    assert master.restarts == []


def test_dead_capture_thread_is_restarted():
    clock = Clock()
    master = FakeMaster(clock, {"CAM_A": make_runtime(clock, capturing=False)})
    restarted = watchdog_for(master, clock).check_once()
    assert restarted == ["CAM_A"]
    assert master.restarts == ["CAM_A"]


def test_dead_processing_thread_is_restarted():
    clock = Clock()
    master = FakeMaster(clock, {"CAM_A": make_runtime(clock, processing=False)})
    assert watchdog_for(master, clock).check_once() == ["CAM_A"]


def test_frozen_frames_are_restarted_even_when_threads_look_alive():
    clock = Clock()
    master = FakeMaster(clock, {"CAM_A": make_runtime(clock, frame_age=45.0), "CAM_B": make_runtime(clock)})
    assert watchdog_for(master, clock).check_once() == ["CAM_A"]


def test_live_streams_reconnecting_on_their_own_are_not_interrupted():
    # A stream source reconnects inside its own loop; while that thread is alive
    # the watchdog must not tear it down just because the capture thread is gone.
    clock = Clock()
    runtime = make_runtime(clock, capturing=False, stream=True, frame_age=5.0)
    runtime.video_source.status = CameraStatus.CONNECTING
    master = FakeMaster(clock, {"CAM_RTSP": runtime})
    assert watchdog_for(master, clock).check_once() == []


def test_failing_camera_backs_off_exponentially():
    clock = Clock()
    master = FakeMaster(clock, {"CAM_A": make_runtime(clock, capturing=False)}, heal_on_restart=False)
    dog = watchdog_for(master, clock)

    assert dog.check_once() == ["CAM_A"]  # first attempt immediately
    clock.now += 14
    assert dog.check_once() == []  # within the 15s backoff
    clock.now += 2
    assert dog.check_once() == ["CAM_A"]  # 16s later: second attempt
    clock.now += 29
    assert dog.check_once() == []  # backoff doubled to 30s
    clock.now += 2
    assert dog.check_once() == ["CAM_A"]
    assert len(master.restarts) == 3


def test_backoff_is_capped():
    clock = Clock()
    master = FakeMaster(clock, {"CAM_A": make_runtime(clock, capturing=False)}, heal_on_restart=False)
    dog = watchdog_for(master, clock, max_backoff=40.0)
    for _ in range(10):
        dog.check_once()
        clock.now += 41
    assert len(master.restarts) == 10


def test_recovery_resets_backoff():
    clock = Clock()
    master = FakeMaster(clock, {"CAM_A": make_runtime(clock, capturing=False)})
    dog = watchdog_for(master, clock)
    assert dog.check_once() == ["CAM_A"]  # restart heals it
    clock.now += 25  # past the startup grace
    master.camera_pipelines["CAM_A"].video_source.last_frame_at = clock.now
    assert dog.check_once() == []  # healthy: failure count cleared

    master.camera_pipelines["CAM_A"].video_source.is_capturing = False
    assert dog.check_once() == ["CAM_A"]  # dies again: restarted at once, no leftover backoff


def test_frames_are_not_judged_during_startup_grace():
    clock = Clock()
    master = FakeMaster(clock, {"CAM_A": make_runtime(clock, capturing=False)})
    dog = watchdog_for(master, clock)
    dog.check_once()
    # The restarted source has not produced a frame yet.
    master.camera_pipelines["CAM_A"].video_source.last_frame_at = clock.now - 100
    master.camera_pipelines["CAM_A"].video_source.is_capturing = False
    clock.now += 5
    assert dog.check_once() == []
    clock.now += 11  # grace and first backoff over: judged again
    assert dog.check_once() == ["CAM_A"]


def test_nothing_happens_while_the_pipeline_is_stopped():
    clock = Clock()
    master = FakeMaster(clock, {"CAM_A": make_runtime(clock, capturing=False)})
    master._started = False
    assert watchdog_for(master, clock).check_once() == []


def test_a_restart_that_raises_does_not_stop_other_cameras():
    clock = Clock()
    master = FakeMaster(
        clock, {"CAM_A": make_runtime(clock, capturing=False), "CAM_B": make_runtime(clock, capturing=False)}
    )
    original = master.restart_camera

    def flaky(camera_id):
        if camera_id == "CAM_A":
            raise RuntimeError("boom")
        return original(camera_id)

    master.restart_camera = flaky
    assert watchdog_for(master, clock).check_once() == ["CAM_B"]


class ExplodingCapture:
    """A capture whose read fails the way OpenCV did when memory ran out."""

    def isOpened(self):
        return True

    def read(self):
        raise MemoryError("Failed to allocate 1555200 bytes")

    def set(self, *_):
        return True

    def release(self):
        pass


def test_capture_thread_crash_is_reported_not_silent():
    source = VideoSource(CameraInfo(camera_id="CAM_A", name="A", source="clip.mp4", fps_limit=0))
    source._cap = ExplodingCapture()
    source._is_file = True
    source._running = True
    source._status = CameraStatus.ONLINE

    source._reader_loop()  # must not raise

    assert source.status == CameraStatus.ERROR
    assert source.is_capturing is False
