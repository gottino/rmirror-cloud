"""
Tests for watcher robustness: handler errors, dead-observer recovery, the
periodic safety-net rescan, and the health fields in /api/status.
"""

import asyncio
import logging
import threading
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from watchdog.events import FileModifiedEvent, FileMovedEvent

from app.config import Config, ReMarkableConfig
from app.sync.manifest import UploadManifest
from app.watcher import file_watcher as fw
from app.watcher.file_watcher import FileWatcher, ReMarkableEventHandler

NB = "nb-aaaa"
BASE_URL = "http://localhost:5556"


@pytest.fixture
def source(tmp_path) -> Path:
    src = tmp_path / "remarkable"
    (src / NB).mkdir(parents=True)
    (src / NB / "p1.rm").write_bytes(b"page one")
    (src / NB / "p2.rm").write_bytes(b"page two")
    (src / f"{NB}.metadata").write_text('{"visibleName": "x"}')
    return src


@pytest.fixture
def manifest(tmp_path):
    return UploadManifest(tmp_path / "manifest.sqlite3", "api.example.test")


@pytest.fixture
def config(test_config, source):
    test_config.remarkable = ReMarkableConfig(source_directory=str(source), watch_enabled=True)
    test_config.sync.sync_interval = 60
    return test_config


class FakeThread:
    def __init__(self):
        self.alive = False

    def is_alive(self):
        return self.alive


class FakeObserver(FakeThread):
    """Stands in for a watchdog Observer: records calls, liveness set by the test."""

    def __init__(self):
        super().__init__()
        self.emitter = FakeThread()
        self.scheduled = []
        self.stopped = False

    @property
    def emitters(self):
        return {self.emitter}

    def schedule(self, handler, path, recursive=False):
        self.scheduled.append((handler, path, recursive))

    def start(self):
        self.alive = self.emitter.alive = True

    def stop(self):
        self.stopped = True
        self.alive = self.emitter.alive = False

    def join(self, timeout=None):
        pass


class FakeTime:
    """Monotonic clock the test advances; sleep() waits until it has been advanced."""

    def __init__(self):
        self.now = 1000.0

    def clock(self):
        return self.now

    async def sleep(self, seconds):
        target = self.now + seconds
        while self.now < target:
            await asyncio.sleep(0.001)

    def advance(self, seconds):
        self.now += seconds


async def wait_for(condition, timeout=5.0):
    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() > deadline:
            raise AssertionError("condition not met in time")
        await asyncio.sleep(0.005)


@pytest.fixture
def fake_time():
    return FakeTime()


@pytest.fixture
def observers():
    return []


@pytest.fixture
def make_watcher(config, manifest, fake_time, observers):
    def factory():
        observer = FakeObserver()
        observers.append(observer)
        return observer

    def make():
        watcher = FileWatcher(
            config,
            MagicMock(),
            manifest=manifest,
            observer_factory=factory,
            clock=fake_time.clock,
            sleep=fake_time.sleep,
        )
        # No upload worker: changes stay in the queue's debounce dict for inspection
        watcher.sync_queue.start = AsyncMock()
        watcher.sync_queue.stop = AsyncMock()
        return watcher

    return make


def pending_names(watcher):
    return sorted(Path(key).name for key in watcher.sync_queue._pending)


async def start_watcher(watcher):
    task = asyncio.create_task(watcher.start())
    await wait_for(lambda: watcher.running)
    return task


async def stop_watcher(watcher, task, fake_time):
    await watcher.stop()
    fake_time.advance(1)  # let the loop's current sleep return
    await asyncio.wait_for(task, timeout=5)


class TestHandlerRobustness:
    def test_error_on_one_event_is_logged_and_next_event_is_queued(self, config, source, caplog):
        queue = MagicMock()
        queue.note_change.side_effect = [RuntimeError("boom"), True]
        handler = ReMarkableEventHandler(queue, config)
        first = source / NB / "p1.rm"
        second = source / NB / "p2.rm"

        with caplog.at_level(logging.INFO, logger=fw.__name__):
            handler.dispatch(FileModifiedEvent(str(first)))  # must not raise
            handler.dispatch(FileModifiedEvent(str(second)))

        assert queue.note_change.call_count == 2
        assert queue.note_change.call_args.args == (second, NB, "rm")
        errors = [r for r in caplog.records if r.levelno == logging.ERROR]
        assert len(errors) == 1 and "p1.rm" in errors[0].getMessage()
        assert handler.last_event_at is not None

    def test_live_detection_is_logged(self, config, source, caplog):
        handler = ReMarkableEventHandler(MagicMock(), config)
        with caplog.at_level(logging.INFO, logger=fw.__name__):
            handler.dispatch(FileMovedEvent(str(source / "tmp"), str(source / NB / "p1.rm")))
        assert "Detected change: p1.rm (rm)" in caplog.text

    def test_real_observer_thread_survives_a_handler_error(self, config, source):
        """With a real watchdog observer thread, an error on one event does not stop it."""
        from watchdog.observers.polling import PollingObserver

        noted = []
        calls = {"n": 0}

        class FlakyQueue:
            def note_change(self, file_path, notebook_uuid, file_type):
                calls["n"] += 1
                if calls["n"] == 1:
                    raise RuntimeError("boom")
                noted.append(file_path.name)
                return True

        observer = PollingObserver(timeout=0.05)
        observer.schedule(ReMarkableEventHandler(FlakyQueue(), config), str(source), recursive=True)
        observer.start()
        try:
            time.sleep(0.2)
            (source / NB / "p1.rm").write_bytes(b"first edit, longer")
            deadline = time.monotonic() + 5
            while calls["n"] == 0 and time.monotonic() < deadline:
                time.sleep(0.02)
            assert calls["n"] >= 1
            (source / NB / "p2.rm").write_bytes(b"second edit, longer")
            while "p2.rm" not in noted and time.monotonic() < deadline:
                time.sleep(0.02)
            assert observer.is_alive()
            assert "p2.rm" in noted
        finally:
            observer.stop()
            observer.join(timeout=5)


class TestObserverHealth:
    async def test_dead_observer_is_replaced_and_rescan_runs(
        self, make_watcher, observers, fake_time, source, manifest, caplog
    ):
        manifest.mark_initialised()  # not a first run: start-up scan queues new files
        watcher = make_watcher()
        task = await start_watcher(watcher)
        assert len(observers) == 1 and watcher.get_health()["observer_alive"]
        assert watcher.last_rescan_reason == "start-up"
        watcher.sync_queue._pending.clear()

        # Observer thread dies (e.g. an error escaped a handler); a page changes meanwhile
        observers[0].alive = False
        (source / NB / "p1.rm").write_bytes(b"edited while no observer was running")
        with caplog.at_level(logging.INFO, logger=fw.__name__):
            fake_time.advance(1)
            await wait_for(lambda: watcher.last_rescan_reason == "observer restart")
            fake_time.advance(1)
            await asyncio.sleep(0.02)

        assert len(observers) == 2
        assert observers[0].stopped
        assert observers[1].scheduled[0][1] == str(source)
        assert watcher.get_health()["observer_alive"] is True
        assert watcher.observer_restarts == 1
        assert "p1.rm" in pending_names(watcher)
        errors = [r for r in caplog.records if r.levelno == logging.ERROR]
        assert len(errors) == 1 and "observer stopped unexpectedly" in errors[0].getMessage()

        await stop_watcher(watcher, task, fake_time)
        assert observers[1].stopped
        fake_time.advance(5)
        await asyncio.sleep(0.02)
        assert len(observers) == 2  # deliberate stop: no restart

    async def test_dead_emitter_counts_as_dead_observer(self, make_watcher, observers, fake_time):
        watcher = make_watcher()
        task = await start_watcher(watcher)
        observers[0].emitter.alive = False  # e.g. FSEvents stream ended
        assert watcher.observer_alive() is False
        fake_time.advance(1)
        await wait_for(lambda: len(observers) == 2)
        await stop_watcher(watcher, task, fake_time)


class TestPeriodicRescan:
    async def test_changed_file_is_picked_up_without_any_event(
        self, make_watcher, fake_time, source, caplog
    ):
        watcher = make_watcher()
        task = await start_watcher(watcher)  # first run: baseline, nothing queued
        assert pending_names(watcher) == []

        (source / NB / "p1.rm").write_bytes(b"edited, but no file event arrived")
        with caplog.at_level(logging.INFO, logger=fw.__name__):
            fake_time.advance(59)
            await asyncio.sleep(0.05)
            assert watcher.last_rescan_reason == "start-up"  # not due yet
            fake_time.advance(1)
            await wait_for(lambda: watcher.last_rescan_reason == "periodic")

        assert pending_names(watcher) == ["p1.rm"]  # p2.rm unchanged: not queued
        assert watcher.last_rescan_result == "1 changed"
        assert "Periodic rescan found 1 changed file(s)" in caplog.text
        await stop_watcher(watcher, task, fake_time)

    async def test_no_log_line_when_nothing_changed(self, make_watcher, fake_time, caplog):
        watcher = make_watcher()
        task = await start_watcher(watcher)
        with caplog.at_level(logging.INFO, logger=fw.__name__):
            fake_time.advance(60)
            await wait_for(lambda: watcher.last_rescan_reason == "periodic")
        assert watcher.last_rescan_result == "0 changed"
        assert "Periodic rescan" not in caplog.text
        assert pending_names(watcher) == []
        await stop_watcher(watcher, task, fake_time)

    async def test_tiny_interval_is_raised_to_minimum(self, make_watcher, config, fake_time):
        config.sync.sync_interval = 0
        watcher = make_watcher()
        task = await start_watcher(watcher)
        fake_time.advance(29)
        await asyncio.sleep(0.05)
        assert watcher.last_rescan_reason == "start-up"
        fake_time.advance(1)
        await wait_for(lambda: watcher.last_rescan_reason == "periodic")
        await stop_watcher(watcher, task, fake_time)

    async def test_rescans_do_not_overlap_and_stop_after_shutdown(self, make_watcher, fake_time):
        watcher = make_watcher()
        task = await start_watcher(watcher)

        release = threading.Event()
        calls = []

        def slow_scan(*args):
            calls.append(args)
            release.wait(5)
            return []

        with patch.object(fw, "scan_for_changes", slow_scan):
            first = asyncio.create_task(watcher._periodic_rescan())
            await wait_for(lambda: len(calls) == 1)
            await watcher._periodic_rescan()  # skipped while the first is running
            fake_time.advance(120)  # the loop's own rescan is due, but one is running
            await asyncio.sleep(0.05)
            assert len(calls) == 1
            release.set()
            await first

            await stop_watcher(watcher, task, fake_time)
            fake_time.advance(600)
            await asyncio.sleep(0.05)
            await watcher._periodic_rescan()  # after stop: does nothing
            assert len(calls) == 1

    async def test_no_periodic_rescan_before_start(self, make_watcher):
        watcher = make_watcher()
        with patch.object(fw, "scan_for_changes", MagicMock(return_value=[])) as scan:
            await watcher._periodic_rescan()
        scan.assert_not_called()


class TestStatusHealth:
    def test_status_exposes_watcher_health(self, test_config_with_token):
        from app.sync.cloud_sync import CloudSync
        from app.web.app import create_app

        config: Config = test_config_with_token
        agent = MagicMock()
        agent.remarkable_folder_missing = False
        agent.file_watcher.sync_queue.get_stats.return_value = {
            "queue_size": 0, "pending": 0, "running": True, "paused_reason": None,
        }
        agent.file_watcher.get_health.return_value = {
            "observer_alive": True,
            "observer_restarts": 1,
            "last_event_at": "2026-11-22T19:40:00",
            "last_rescan_at": "2026-11-22T19:41:00",
            "last_rescan_reason": "periodic",
            "last_rescan_result": "1 changed",
        }
        flask_app = create_app(config, CloudSync(config), agent=agent)
        flask_app.config["TESTING"] = True

        watching = flask_app.test_client().get("/api/status", base_url=BASE_URL).get_json()["watching"]
        assert watching["observer_alive"] is True
        assert watching["last_event_at"] == "2026-11-22T19:40:00"
        assert watching["last_rescan_at"] == "2026-11-22T19:41:00"
        assert watching["last_rescan_result"] == "1 changed"
        assert watching["observer_restarts"] == 1

    def test_status_without_watcher_has_empty_health(self, test_config_with_token):
        from app.sync.cloud_sync import CloudSync
        from app.web.app import create_app

        flask_app = create_app(test_config_with_token, CloudSync(test_config_with_token), agent=None)
        flask_app.config["TESTING"] = True
        watching = flask_app.test_client().get("/api/status", base_url=BASE_URL).get_json()["watching"]
        assert watching["observer_alive"] is False
        assert watching["last_event_at"] is None
        assert watching["last_rescan_at"] is None

    def test_get_health_reports_real_watcher_state(self, config, manifest):
        watcher = FileWatcher(config, MagicMock(), manifest=manifest, observer_factory=FakeObserver)
        health = watcher.get_health()
        assert health["observer_alive"] is False
        assert health["last_event_at"] is None and health["last_rescan_at"] is None
