"""
Thread hand-offs in the Agent: watcher start idempotency, shutdown order,
watchdog events without an event loop, and tray status marshalling.
"""

import asyncio
import logging
import threading
import time
from unittest.mock import patch

import httpx
import pytest

from app.agent_loop import AgentLoop
from app.config import ReMarkableConfig
from app.main import Agent
from app.sync.cloud_sync import CloudSync
from app.tray.status import StatusRelay


class FakeFileWatcher:
    """Stands in for FileWatcher: start() blocks until stop(), like the real one."""

    instances: list["FakeFileWatcher"] = []

    def __init__(self, config, cloud_sync, on_status=None):
        self.started = threading.Event()
        self.stopped = threading.Event()
        self.running = False
        self.start_thread: int | None = None
        FakeFileWatcher.instances.append(self)

    async def start(self):
        self.start_thread = threading.get_ident()
        self.running = True
        self.started.set()
        while self.running:
            await asyncio.sleep(0.01)

    async def stop(self):
        self.running = False
        self.stopped.set()


@pytest.fixture
def fake_watcher():
    FakeFileWatcher.instances = []
    with patch("app.watcher.file_watcher.FileWatcher", FakeFileWatcher):
        yield FakeFileWatcher


@pytest.fixture
def config(test_config_with_token, tmp_path):
    source = tmp_path / "remarkable"
    source.mkdir()
    test_config_with_token.remarkable = ReMarkableConfig(source_directory=str(source), watch_enabled=True)
    return test_config_with_token


@pytest.fixture
def agent(config):
    agent = Agent(config, agent_loop=AgentLoop())
    agent.loop.start()
    agent.running = True
    cloud_sync = CloudSync(config)
    cloud_sync.client = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={})))
    cloud_sync.authenticated = True
    agent.cloud_sync = cloud_sync
    yield agent
    agent.shutdown(timeout=5)


def _wait(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


class TestWatcherStart:
    def test_two_concurrent_starts_run_one_watcher(self, agent, fake_watcher):
        barrier = threading.Barrier(2)
        results = []

        def call():
            barrier.wait()
            results.append(agent.start_file_watcher_sync())

        threads = [threading.Thread(target=call) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(5)

        assert sorted(results) == [False, True]
        assert _wait(lambda: fake_watcher.instances and fake_watcher.instances[0].started.is_set())
        time.sleep(0.05)  # give a wrongly scheduled second watcher time to appear
        assert len(fake_watcher.instances) == 1

    def test_many_concurrent_starts_run_one_watcher(self, agent, fake_watcher):
        barrier = threading.Barrier(8)
        results = []

        def call():
            barrier.wait()
            results.append(agent.start_file_watcher_sync())

        threads = [threading.Thread(target=call) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(5)

        assert results.count(True) == 1
        assert _wait(lambda: fake_watcher.instances and fake_watcher.instances[0].started.is_set())
        assert len(fake_watcher.instances) == 1

    def test_watcher_runs_on_agent_loop_thread(self, agent, fake_watcher):
        assert agent.start_file_watcher_sync() is True
        assert _wait(lambda: fake_watcher.instances and fake_watcher.instances[0].started.is_set())
        assert fake_watcher.instances[0].start_thread == agent.loop._thread.ident
        assert agent.file_watcher is fake_watcher.instances[0]

    def test_start_while_running_does_nothing(self, agent, fake_watcher):
        assert agent.start_file_watcher_sync() is True
        assert _wait(lambda: fake_watcher.instances and fake_watcher.instances[0].started.is_set())
        assert agent.start_file_watcher_sync() is False
        assert len(fake_watcher.instances) == 1

    def test_can_start_again_after_watcher_ended(self, agent, fake_watcher):
        assert agent.start_file_watcher_sync() is True
        assert _wait(lambda: fake_watcher.instances and fake_watcher.instances[0].started.is_set())
        agent.loop.run(fake_watcher.instances[0].stop(), timeout=5)
        assert _wait(lambda: agent._watcher_state == Agent.WATCHER_IDLE)
        assert agent.start_file_watcher_sync() is True
        assert _wait(lambda: len(fake_watcher.instances) == 2)

    def test_failed_watcher_start_can_be_retried(self, agent, fake_watcher):
        class Failing(FakeFileWatcher):
            async def start(self):
                raise FileNotFoundError("folder vanished")

        with patch("app.watcher.file_watcher.FileWatcher", Failing):
            assert agent.start_file_watcher_sync() is True
            assert _wait(lambda: agent._watcher_state == Agent.WATCHER_IDLE)
        assert agent.start_file_watcher_sync() is True

    def test_not_started_without_sign_in(self, agent, fake_watcher):
        agent.cloud_sync.authenticated = False
        assert agent.start_file_watcher_sync() is False
        assert fake_watcher.instances == []

    def test_not_started_after_shutdown(self, agent, fake_watcher):
        agent.shutdown(timeout=5)
        assert agent.start_file_watcher_sync() is False
        assert fake_watcher.instances == []


class TestShutdown:
    def test_shutdown_stops_watcher_closes_client_and_joins_loop(self, agent, fake_watcher, caplog):
        assert agent.start_file_watcher_sync() is True
        assert _wait(lambda: fake_watcher.instances and fake_watcher.instances[0].started.is_set())
        # Use the client on the loop so it holds loop-bound state
        agent.loop.run(agent.cloud_sync.client.get("http://backend.test/x"), timeout=5)
        thread = agent.loop._thread

        with caplog.at_level(logging.DEBUG):
            agent.shutdown(timeout=5)

        assert fake_watcher.instances[0].stopped.is_set()
        assert agent.cloud_sync.client is None
        assert not thread.is_alive()
        assert agent.loop.loop.is_closed()
        assert agent.loop.is_running is False
        assert not [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert not [r for r in caplog.records if "Event loop is closed" in r.getMessage()]

    def test_shutdown_is_idempotent(self, agent):
        agent.shutdown(timeout=5)
        agent.shutdown(timeout=5)

    def test_agent_start_and_shutdown_end_to_end(self, config, fake_watcher):
        """Agent.start() on the loop starts the watcher once; a later sign-in start is a no-op."""
        config.web.enabled = False
        agent = Agent(config, agent_loop=AgentLoop())

        async def fake_authenticate(self):
            self.authenticated = True
            return True

        async def fake_quota(self):
            return {"used": 1, "limit": 200}

        with patch.object(CloudSync, "authenticate", fake_authenticate), \
                patch.object(CloudSync, "get_quota_status", fake_quota):
            agent.loop.start()
            future = agent.loop.submit(agent.start())
            assert _wait(lambda: fake_watcher.instances and fake_watcher.instances[0].started.is_set())
            assert agent.start_file_watcher_sync() is False
            agent.shutdown(timeout=5)

        assert future.done()
        assert len(fake_watcher.instances) == 1
        assert fake_watcher.instances[0].stopped.is_set()


class TestWatchdogHandoff:
    def test_events_from_a_thread_without_loop_reach_the_queue(self, config, tmp_path):
        from watchdog.events import FileModifiedEvent

        from app.sync.manifest import UploadManifest
        from app.sync.queue import SyncQueue
        from app.watcher.file_watcher import ReMarkableEventHandler

        source = tmp_path / "remarkable"
        page = source / "nb" / "p.rm"
        page.parent.mkdir(parents=True)
        page.write_bytes(b"x")
        queue = SyncQueue(config, CloudSync(config), manifest=UploadManifest(tmp_path / "m.sqlite3", "h"))
        handler = ReMarkableEventHandler(queue, config)

        def fire():
            for _ in range(20):
                handler.on_any_event(FileModifiedEvent(str(page)))

        with patch("asyncio.run", side_effect=AssertionError("asyncio.run must not be used")):
            threads = [threading.Thread(target=fire) for _ in range(4)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(5)

        assert queue.get_stats()["pending"] == 1  # debounced to one path


class TestStatusRelay:
    def test_post_does_not_apply_until_flush(self):
        applied = []
        relay = StatusRelay(applied.append)
        relay.post("Watching")
        assert applied == []
        assert relay.flush() is True
        assert applied == ["Watching"]
        assert relay.flush() is False
        assert applied == ["Watching"]

    def test_only_newest_status_is_applied(self):
        applied = []
        relay = StatusRelay(applied.append)
        for status in ("Starting...", "Connected", "Watching"):
            relay.post(status)
        relay.flush()
        assert applied == ["Watching"]

    def test_apply_only_runs_on_flushing_thread(self):
        applied_on = []
        relay = StatusRelay(lambda status: applied_on.append((status, threading.get_ident())))

        def post_many(i):
            for n in range(50):
                relay.post(f"status {i}-{n}")

        threads = [threading.Thread(target=post_many, args=(i,)) for i in range(6)]
        for t in threads:
            t.start()
        while any(t.is_alive() for t in threads):
            relay.flush()
        for t in threads:
            t.join()
        relay.flush()

        assert applied_on
        assert {thread_id for _, thread_id in applied_on} == {threading.get_ident()}
        assert applied_on[-1][0].endswith("-49")

    def test_status_module_does_not_need_rumps(self):
        import importlib
        import sys

        import app.tray.status

        # With rumps unimportable, the relay module (and the tray package) still import
        with patch.dict(sys.modules, {"rumps": None}):
            importlib.reload(importlib.import_module("app.tray"))
            importlib.reload(app.tray.status)
