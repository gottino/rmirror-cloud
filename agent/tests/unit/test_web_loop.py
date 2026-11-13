"""
Flask routes hand their coroutines to the agent's one event loop.

Real routes are driven against a fake backend (httpx MockTransport) while the
agent loop is running, from several threads at once, with watcher events
arriving on another thread at the same time.
"""

import asyncio
import threading
import time
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

from app.agent_loop import AgentLoop
from app.config import Config, ReMarkableConfig
from app.sync.cloud_sync import CloudSync
from app.sync.manifest import UploadManifest
from app.sync.queue import SyncQueue
from app.watcher.file_watcher import ReMarkableEventHandler
from app.web import routes
from app.web.app import create_app

PORT = 5556  # matches test_config
BASE_URL = f"http://localhost:{PORT}"
NB = "nb-loop"


class FakeBackend:
    """Async MockTransport handler that records which thread and loop served each request."""

    def __init__(self, delay: float = 0.005):
        self.delay = delay
        self.lock = threading.Lock()
        self.calls: list[tuple[str, str, int, asyncio.AbstractEventLoop]] = []
        self.hold: asyncio.Event | None = None

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        with self.lock:
            self.calls.append(
                (request.method, request.url.path, threading.get_ident(), asyncio.get_running_loop())
            )
        await asyncio.sleep(self.delay)
        path = request.url.path
        if path.endswith("/sync/stats"):
            return httpx.Response(200, json={"total_pages": 7})
        if path.endswith("/quota/status"):
            return httpx.Response(200, json={"used": 3, "limit": 200, "is_exhausted": False})
        if path.endswith("/users/me"):
            return httpx.Response(200, json={"id": 1, "email": "user@example.test"})
        if path.endswith("/sync/deleted-notebooks"):
            return httpx.Response(200, json={"deleted_notebooks": [{"notebook_uuid": "gone"}]})
        if path.endswith("/processing/rm-file"):
            return httpx.Response(200, json={"success": True})
        return httpx.Response(200, json={"success": True})

    def paths(self, suffix: str) -> list:
        with self.lock:
            return [c for c in self.calls if c[1].endswith(suffix)]


@pytest.fixture
def save_mock():
    with patch.object(Config, "save", autospec=True) as save:
        yield save


@pytest.fixture
def config(test_config_with_token, save_mock):
    test_config_with_token.api.use_clerk_auth = True
    return test_config_with_token


@pytest.fixture
def agent_loop():
    loop = AgentLoop()
    loop.start()
    yield loop
    loop.stop()


@pytest.fixture
def backend():
    return FakeBackend()


@pytest.fixture
def cloud_sync(config, backend):
    sync = CloudSync(config)
    sync.client = httpx.AsyncClient(transport=httpx.MockTransport(backend))
    sync.authenticated = True
    return sync


@pytest.fixture
def app(config, cloud_sync, agent_loop):
    flask_app = create_app(config, cloud_sync, agent=None, agent_loop=agent_loop)
    flask_app.config["TESTING"] = True
    return flask_app


def _get(app, path):
    return app.test_client().get(path, base_url=BASE_URL)


class TestRoutesOnAgentLoop:
    def test_route_runs_on_agent_loop_and_keeps_client(self, app, cloud_sync, backend, agent_loop):
        client_before = cloud_sync.client
        resp = _get(app, "/api/quota")
        assert resp.status_code == 200
        assert resp.get_json()["used"] == 3
        (_, _, thread_id, loop) = backend.paths("/quota/status")[0]
        assert loop is agent_loop.loop
        assert thread_id == agent_loop._thread.ident
        # The long-lived client is never dropped by a request
        assert cloud_sync.client is client_before

    def test_concurrent_requests_from_many_threads(self, app, cloud_sync, backend, agent_loop):
        client_before = cloud_sync.client
        expected = {
            "/api/quota": lambda d: d["limit"] == 200,
            "/api/sync/status": lambda d: d["total_pages"] == 7,
            "/api/auth/me": lambda d: d["email"] == "user@example.test",
            "/api/deleted-notebooks": lambda d: d["deleted_notebooks"][0]["notebook_uuid"] == "gone",
        }
        failures = []
        start = threading.Barrier(12)

        def worker(i):
            path = list(expected)[i % len(expected)]
            start.wait()
            for _ in range(5):
                resp = _get(app, path)
                if resp.status_code != 200 or not expected[path](resp.get_json()):
                    failures.append((path, resp.status_code, resp.get_data(as_text=True)))

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(12)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(30)

        assert failures == []
        assert len(backend.calls) == 60
        # Every backend call ran on the one agent loop, on its thread
        assert {c[3] for c in backend.calls} == {agent_loop.loop}
        assert {c[2] for c in backend.calls} == {agent_loop._thread.ident}
        assert cloud_sync.client is client_before

    def test_routes_and_watcher_events_concurrently(
        self, app, config, cloud_sync, backend, agent_loop, tmp_path
    ):
        """Watchdog-thread events upload through the queue worker while Flask threads call the backend."""
        from watchdog.events import FileModifiedEvent

        source = tmp_path / "remarkable"
        (source / NB).mkdir(parents=True)
        pages = []
        for i in range(6):
            page = source / NB / f"p{i}.rm"
            page.write_bytes(f"page {i}".encode())
            pages.append(page)
        config.remarkable = ReMarkableConfig(source_directory=str(source), watch_enabled=True)
        config.sync.cooldown_seconds = 0

        manifest = UploadManifest(tmp_path / "manifest.sqlite3", "api.example.test")

        async def make_queue():
            queue = SyncQueue(config, cloud_sync, manifest=manifest)
            await queue.start()
            return queue

        sync_queue = agent_loop.run(make_queue(), timeout=5)
        handler = ReMarkableEventHandler(sync_queue, config)
        failures = []

        def watchdog_thread():
            # No event loop on this thread, like watchdog's observer thread
            for page in pages:
                handler.on_any_event(FileModifiedEvent(str(page)))

        def flask_thread():
            for _ in range(5):
                resp = _get(app, "/api/quota")
                if resp.status_code != 200:
                    failures.append(resp.status_code)

        with patch("asyncio.run", side_effect=AssertionError("asyncio.run must not be used")):
            threads = [threading.Thread(target=watchdog_thread)] + [
                threading.Thread(target=flask_thread) for _ in range(4)
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join(30)

            deadline = time.monotonic() + 10
            while len(backend.paths("/processing/rm-file")) < len(pages) and time.monotonic() < deadline:
                time.sleep(0.02)

        agent_loop.run(sync_queue.stop(), timeout=5)

        assert failures == []
        assert len(backend.paths("/processing/rm-file")) == len(pages)
        assert {c[3] for c in backend.calls} == {agent_loop.loop}


class TestLoopErrors:
    def test_timeout_returns_json_error_and_loop_recovers(self, app, backend, agent_loop):
        backend.delay = 2.0
        with patch.object(routes, "QUICK_TIMEOUT_SECONDS", 0.1):
            resp = _get(app, "/api/quota")
        assert resp.status_code == 504
        body = resp.get_json()
        assert body["error"] == "timeout"
        assert body["success"] is False
        backend.delay = 0
        assert _get(app, "/api/quota").status_code == 200

    def test_no_loop_returns_json_error(self, config, cloud_sync):
        flask_app = create_app(config, cloud_sync, agent=None, agent_loop=None)
        resp = flask_app.test_client().get("/api/quota", base_url=BASE_URL)
        assert resp.status_code == 503
        assert resp.get_json()["error"] == "agent_not_ready"

    def test_stopped_loop_returns_json_error(self, config, cloud_sync):
        stopped = AgentLoop()
        stopped.start()
        stopped.stop()
        flask_app = create_app(config, cloud_sync, agent=None, agent_loop=stopped)
        resp = flask_app.test_client().get("/api/sync/status", base_url=BASE_URL)
        assert resp.status_code == 503

    def test_environment_switch_keeps_http_client(self, app, cloud_sync):
        client_before = cloud_sync.client
        resp = app.test_client().post(
            "/api/auth/environment", json={"environment": "staging"}, base_url=BASE_URL
        )
        assert resp.status_code == 200
        assert cloud_sync.client is client_before
        assert cloud_sync.authenticated is False


class FakeInitialSync:
    """Stands in for InitialSync; run() waits until the test releases it."""

    instances: list["FakeInitialSync"] = []

    def __init__(self, config, cloud_sync):
        self.release = threading.Event()
        self.error: Exception | None = None
        self.ran_on: int | None = None
        self.selected = "unset"
        FakeInitialSync.instances.append(self)

    async def run(self, selected_uuids=None):
        self.ran_on = threading.get_ident()
        self.selected = selected_uuids
        while not self.release.is_set():
            await asyncio.sleep(0.01)
        if self.error:
            raise self.error
        return {"notebooks": 2, "pages": 9, "failed": 0, "skipped": 0, "rate_limited": 0}


@pytest.fixture
def fake_initial_sync():
    FakeInitialSync.instances = []
    with patch("app.sync.initial_sync.InitialSync", FakeInitialSync):
        yield FakeInitialSync


def _wait_for_state(client, state, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        data = client.get("/api/sync/initial/status", base_url=BASE_URL).get_json()
        if data["state"] == state:
            return data
        time.sleep(0.01)
    raise AssertionError(f"initial sync never reached {state}: {data}")


class TestInitialSync:
    def test_status_starts_idle(self, app):
        data = _get(app, "/api/sync/initial/status").get_json()
        assert data["state"] == "idle"
        assert data["stats"] is None

    def test_start_returns_202_and_runs_on_agent_loop(self, app, agent_loop, fake_initial_sync):
        client = app.test_client()
        started = time.monotonic()
        resp = client.post("/api/sync/initial", base_url=BASE_URL)
        assert time.monotonic() - started < 2
        assert resp.status_code == 202
        assert resp.get_json()["state"] == "running"
        assert _get(app, "/api/sync/initial/status").get_json()["state"] == "running"

        (job,) = fake_initial_sync.instances
        job.release.set()
        data = _wait_for_state(client, "done")
        assert data["stats"]["pages"] == 9
        assert data["finished_at"] is not None
        assert job.ran_on == agent_loop._thread.ident
        assert job.selected is None  # sync_all_notebooks is the default

    def test_second_start_while_running_is_refused(self, app, fake_initial_sync):
        client = app.test_client()
        assert client.post("/api/sync/initial", base_url=BASE_URL).status_code == 202
        second = client.post("/api/sync/initial", base_url=BASE_URL)
        assert second.status_code == 409
        assert second.get_json()["state"] == "running"
        assert len(fake_initial_sync.instances) == 1
        fake_initial_sync.instances[0].release.set()
        _wait_for_state(client, "done")
        # Once finished it can be started again
        assert client.post("/api/sync/initial", base_url=BASE_URL).status_code == 202
        fake_initial_sync.instances[1].release.set()
        _wait_for_state(client, "done")

    def test_failure_is_reported_in_status(self, app, fake_initial_sync):
        client = app.test_client()
        assert client.post("/api/sync/initial", base_url=BASE_URL).status_code == 202
        job = fake_initial_sync.instances[0]
        job.error = RuntimeError("backend exploded")
        job.release.set()
        data = _wait_for_state(client, "error")
        assert data["message"] == "backend exploded"

    def test_requires_sign_in(self, app, cloud_sync, fake_initial_sync):
        cloud_sync.authenticated = False
        resp = app.test_client().post("/api/sync/initial", base_url=BASE_URL)
        assert resp.status_code == 401
        assert fake_initial_sync.instances == []
        assert _get(app, "/api/sync/initial/status").get_json()["state"] == "idle"

    def test_without_loop_returns_503_and_stays_idle(self, config, cloud_sync, fake_initial_sync):
        flask_app = create_app(config, cloud_sync, agent=None, agent_loop=None)
        client = flask_app.test_client()
        resp = client.post("/api/sync/initial", base_url=BASE_URL)
        assert resp.status_code == 503
        assert client.get("/api/sync/initial/status", base_url=BASE_URL).get_json()["state"] == "idle"

    def test_template_polls_status_endpoint(self):
        template = Path(routes.__file__).parent / "templates" / "index.html"
        assert "/api/sync/initial/status" in template.read_text()
