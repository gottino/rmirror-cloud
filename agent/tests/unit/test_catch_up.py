"""
First contact with an API host: the catch-up against GET /sync/stored-pages
(app/sync/catch_up.py), the account binding of the upload manifest, and what the
local API reports about it (catch_up, first_sync, on_server, synced_pages).
"""

import asyncio
import hashlib
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from watchdog.events import FileModifiedEvent

from app.agent_loop import AgentLoop
from app.config import Config
from app.sync import catch_up as catch_up_module
from app.sync.catch_up import parse_stored_pages
from app.sync.cloud_sync import (
    AuthenticationRequiredError,
    CloudSync,
    CloudSyncError,
    StoredPagesUnavailableError,
)
from app.sync.initial_sync import PagePlanner
from app.sync.manifest import UploadManifest, fingerprint_file
from app.sync.queue import PAUSED_SIGN_IN
from app.watcher.file_watcher import FileWatcher, ReMarkableEventHandler
from app.web.app import create_app

PORT = 5556
BASE_URL = f"http://127.0.0.1:{PORT}"
TOKEN = "b" * 64
HEADERS = {"X-RMirror-App-Token": TOKEN}
EMAIL = "user@example.test"

PRODUCTION = "https://rmirror.io/api/v1"
STAGING = "https://staging.rmirror.io/api/v1"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def page_bytes(nb: str, i: int) -> bytes:
    return f"{nb} page {i}".encode()


def write_notebook(root: Path, uuid: str, pages: int, parent: str = "") -> None:
    """A notebook with pages p0..p<n-1>; the .content order is oldest first."""
    (root / f"{uuid}.metadata").write_text(json.dumps({"visibleName": uuid, "type": "DocumentType", "parent": parent}))
    ids = [f"{uuid}-p{i}" for i in range(pages)]
    (root / f"{uuid}.content").write_text(json.dumps({"pages": ids}))
    (root / uuid).mkdir()
    for i, pid in enumerate(ids):
        (root / uuid / f"{pid}.rm").write_bytes(page_bytes(uuid, i))


def server_page(nb: str, i: int, data: bytes | None = None, status: str = "completed") -> dict:
    return {
        "page_uuid": f"{nb}-p{i}",
        "file_hash": sha(data if data is not None else page_bytes(nb, i)),
        "ocr_status": status,
    }


def stored(notebooks: dict[str, list[dict]]) -> dict:
    return {
        "notebooks": [{"notebook_uuid": nb, "pages": pages} for nb, pages in notebooks.items()],
        "notebook_count": len(notebooks),
        "page_count": sum(len(p) for p in notebooks.values()),
    }


class Backend:
    """httpx MockTransport handler: stored-pages and users/me."""

    def __init__(self):
        self.stored: dict | None = stored({})
        self.stored_status = 200
        self.stored_body: object = {}
        self.email = EMAIL
        self.calls: list[str] = []

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        self.calls.append(f"{request.method} {request.url.host}{path}")
        if path.endswith("/sync/stored-pages"):
            if self.stored_status != 200:
                return httpx.Response(self.stored_status, json=self.stored_body)
            if isinstance(self.stored, str):
                return httpx.Response(200, text=self.stored)
            return httpx.Response(200, json=self.stored)
        if path.endswith("/users/me"):
            return httpx.Response(200, json={"id": 7, "email": self.email})
        if path.endswith("/sync/stats"):
            return httpx.Response(200, json={})
        return httpx.Response(200, json={})

    def stored_calls(self) -> int:
        return sum(1 for c in self.calls if c.endswith("/sync/stored-pages"))


@pytest.fixture
def library(tmp_path) -> Path:
    root = tmp_path / "desktop"
    root.mkdir()
    write_notebook(root, "alpha", 3)
    write_notebook(root, "beta", 2)
    write_notebook(root, "gamma", 4)
    (root / "folder1.metadata").write_text(json.dumps({"visibleName": "Work", "type": "CollectionType"}))
    return root


@pytest.fixture
def config(test_config_with_token, library):
    test_config_with_token.remarkable.source_directory = str(library)
    test_config_with_token.remarkable.watch_enabled = True
    test_config_with_token.sync.sync_all_notebooks = False
    test_config_with_token.sync.selected_notebooks = ["alpha", "gamma"]
    with patch.object(Config, "save", autospec=True):
        yield test_config_with_token


@pytest.fixture
def backend():
    return Backend()


@pytest.fixture
def cloud_sync(config, backend):
    sync = CloudSync(config)
    sync.client = httpx.AsyncClient(transport=httpx.MockTransport(backend))
    sync.authenticated = True
    sync.user_email = EMAIL
    return sync


@pytest.fixture
def manifest(config):
    return UploadManifest.for_config(config)


@pytest.fixture
def watcher(config, cloud_sync, manifest):
    return FileWatcher(config, cloud_sync, manifest=manifest)


def queued(watcher) -> list[str]:
    """Queued files as '<parent>/<name>' (pages) or '<name>'."""
    result = []
    for key in watcher.sync_queue._pending:
        p = Path(key)
        result.append(f"{p.parent.name}/{p.name}" if p.suffix == ".rm" else p.name)
    return sorted(result)


def queued_pages(watcher) -> list[str]:
    return [name for name in queued(watcher) if name.endswith(".rm")]


def entry(manifest, path):
    return manifest.get(path)


def page(library, nb, i) -> Path:
    return library / nb / f"{nb}-p{i}.rm"


# ----------------------------------------------------------------------
# Watcher side
# ----------------------------------------------------------------------


class TestSignedOut:
    async def test_no_baseline_and_no_upload_while_signed_out(self, watcher, cloud_sync, manifest, library, backend):
        cloud_sync.authenticated = False
        assert await watcher.rescan(reason="start-up") == 0
        assert not manifest.is_initialised()
        assert not manifest.has_entries()
        assert backend.calls == []
        assert queued(watcher) == []
        assert watcher.last_rescan_result == "waiting for catch-up (sign_in)"

    async def test_events_are_not_queued_before_the_catch_up(self, watcher, cloud_sync, library, config):
        cloud_sync.authenticated = False
        handler = ReMarkableEventHandler(watcher.sync_queue, config, gate=watcher.catch_up.gate_open)
        handler.dispatch(FileModifiedEvent(str(page(library, "alpha", 0))))
        assert queued(watcher) == []

        cloud_sync.authenticated = True
        await watcher.rescan(reason="reconnect")
        watcher.sync_queue._pending.clear()
        handler.dispatch(FileModifiedEvent(str(page(library, "alpha", 0))))
        assert queued(watcher) == ["alpha/alpha-p0.rm"]


class TestFirstContact:
    async def test_server_has_everything(self, watcher, manifest, library, backend):
        backend.stored = stored({
            "alpha": [server_page("alpha", i) for i in range(3)],
            "beta": [server_page("beta", i) for i in range(2)],
            "gamma": [server_page("gamma", i) for i in range(4)],
        })
        await watcher.rescan(reason="start-up")

        assert manifest.is_initialised()
        assert manifest.account() == EMAIL
        assert queued_pages(watcher) == []  # no page is uploaded
        for nb, n in (("alpha", 3), ("beta", 2), ("gamma", 4)):
            for i in range(n):
                e = entry(manifest, page(library, nb, i))
                assert e is not None and not e.is_baseline, (nb, i)
        # The selected notebooks' .metadata/.content go once (renames made meanwhile)
        assert queued(watcher) == ["alpha.content", "alpha.metadata", "gamma.content", "gamma.metadata"]
        assert manifest.get_meta("catch_up") == "done"
        assert manifest.server_notebooks() == {"alpha", "beta", "gamma"}

    async def test_older_versions_and_missing_page_are_left_to_upload(self, watcher, manifest, library, backend):
        backend.stored = stored({
            "alpha": [
                server_page("alpha", 0, b"older version of p0"),
                server_page("alpha", 1),
                server_page("alpha", 2),
            ],
            "gamma": [
                server_page("gamma", 0),
                server_page("gamma", 1, b"older version of g1"),
                server_page("gamma", 2),
                # gamma-p3 is not on the server
            ],
        })
        await watcher.rescan(reason="start-up")

        assert queued_pages(watcher) == ["alpha/alpha-p0.rm", "gamma/gamma-p1.rm", "gamma/gamma-p3.rm"]
        for nb, i in (("alpha", 0), ("gamma", 1), ("gamma", 3)):
            assert entry(manifest, page(library, nb, i)) is None
        for nb, i in (("alpha", 1), ("alpha", 2), ("gamma", 0), ("gamma", 2)):
            assert not entry(manifest, page(library, nb, i)).is_baseline
        # beta is not selected and not on the server: baseline as before
        assert entry(manifest, page(library, "beta", 0)).is_baseline

    async def test_failed_page_on_server_is_left_to_upload(self, watcher, manifest, library, backend):
        backend.stored = stored({
            "alpha": [
                server_page("alpha", 0, status="failed"),
                server_page("alpha", 1, status="not_synced"),
                server_page("alpha", 2, status="pending_quota"),
            ],
        })
        await watcher.rescan(reason="start-up")
        assert "alpha/alpha-p0.rm" in queued_pages(watcher)
        assert "alpha/alpha-p1.rm" in queued_pages(watcher)
        assert not entry(manifest, page(library, "alpha", 2)).is_baseline

    async def test_page_limit_is_respected(self, watcher, config, manifest, library, backend):
        config.sync.max_pages_per_notebook = 2
        config.sync.selected_notebooks = ["gamma"]
        await watcher.rescan(reason="start-up")
        # Newest two (p3, p2) upload; the older ones are baselined
        assert queued_pages(watcher) == ["gamma/gamma-p2.rm", "gamma/gamma-p3.rm"]
        assert entry(manifest, page(library, "gamma", 0)).is_baseline
        assert entry(manifest, page(library, "gamma", 1)).is_baseline

    async def test_unselected_notebook_on_server(self, watcher, manifest, library, backend):
        backend.stored = stored({"beta": [server_page("beta", 0), server_page("beta", 1, b"old")]})
        await watcher.rescan(reason="start-up")
        assert not entry(manifest, page(library, "beta", 0)).is_baseline  # on the server
        assert entry(manifest, page(library, "beta", 1)).is_baseline  # differs: baseline
        assert not any(name.startswith("beta") for name in queued(watcher))
        assert manifest.get_meta("selection_notice") == "pending"

    async def test_folder_metadata_baselined_with_a_selection(self, watcher, manifest, library):
        await watcher.rescan(reason="start-up")
        assert entry(manifest, library / "folder1.metadata").is_baseline
        assert "folder1.metadata" not in queued(watcher)

    async def test_nothing_uploads_without_an_explicit_selection(self, watcher, config, manifest, library, backend):
        """sync_all (the default: fresh install, 1.x without a saved selection): the old protection."""
        config.sync.sync_all_notebooks = True
        config.sync.selected_notebooks = []
        await watcher.rescan(reason="start-up")
        assert queued(watcher) == []
        assert entry(manifest, library / "folder1.metadata").is_baseline
        for nb, n in (("alpha", 3), ("beta", 2), ("gamma", 4)):
            for i in range(n):
                assert entry(manifest, page(library, nb, i)).is_baseline
            assert entry(manifest, library / f"{nb}.metadata").is_baseline

    async def test_server_matches_still_recorded_without_a_selection(self, watcher, config, manifest, library, backend):
        config.sync.sync_all_notebooks = True
        backend.stored = stored({"beta": [server_page("beta", 0), server_page("beta", 1, b"old")]})
        await watcher.rescan(reason="start-up")
        assert queued(watcher) == []
        assert not entry(manifest, page(library, "beta", 0)).is_baseline
        assert entry(manifest, page(library, "beta", 1)).is_baseline
        # The notebook list shows everything ticked under sync_all: no notice
        assert manifest.get_meta("selection_notice") is None

    async def test_notebook_files_without_anything_to_upload_are_baselined(
        self, watcher, config, manifest, library, backend
    ):
        """A selected PDF without annotations or an empty notebook the server does not know:
        its .metadata/.content would answer notebook_not_found on every scan."""
        (library / "doc.metadata").write_text(json.dumps({"visibleName": "Doc", "type": "DocumentType"}))
        (library / "doc.content").write_text(json.dumps({"pages": []}))
        (library / "doc.pdf").write_bytes(b"%PDF")
        (library / "empty.metadata").write_text(json.dumps({"visibleName": "Empty", "type": "DocumentType"}))
        (library / "empty.content").write_text(json.dumps({"pages": []}))
        (library / "alpha").joinpath("alpha-p0.pagedata").write_text("Blank")
        config.sync.selected_notebooks = ["alpha", "doc", "empty"]
        backend.stored = stored({"alpha": [server_page("alpha", i) for i in range(3)]})
        await watcher.rescan(reason="start-up")

        for name in ("doc.metadata", "doc.content", "doc.pdf", "empty.metadata", "empty.content"):
            assert entry(manifest, library / name).is_baseline, name
        assert entry(manifest, library / "alpha" / "alpha-p0.pagedata").is_baseline
        # alpha: the server has the notebook, so its .metadata/.content go once
        assert queued(watcher) == ["alpha.content", "alpha.metadata"]

    async def test_older_backend_falls_back_to_uploading_the_selection(self, watcher, manifest, library, backend):
        backend.stored_status = 404
        backend.stored_body = {"detail": "Not Found"}
        await watcher.rescan(reason="start-up")
        assert manifest.is_initialised()
        assert manifest.get_meta("catch_up") == "unavailable"
        assert queued_pages(watcher) == sorted(
            [f"alpha/alpha-p{i}.rm" for i in range(3)] + [f"gamma/gamma-p{i}.rm" for i in range(4)]
        )
        assert entry(manifest, page(library, "beta", 0)).is_baseline
        assert manifest.server_notebooks() == set()

    async def test_network_error_stays_pending_then_reconciles(self, config, cloud_sync, manifest, library, backend):
        now = [1000.0]
        watcher = FileWatcher(config, cloud_sync, manifest=manifest, clock=lambda: now[0])
        backend.stored_status = 503
        assert await watcher.rescan(reason="start-up") == 0
        assert not manifest.is_initialised() and not manifest.has_entries()
        assert queued(watcher) == []
        assert not watcher.catch_up.retry_due()

        # A periodic rescan inside the backoff does not ask again
        await watcher.rescan(reason="periodic")
        assert backend.stored_calls() == 1

        now[0] += watcher.catch_up.FIRST_RETRY_SECONDS
        assert watcher.catch_up.retry_due()
        backend.stored_status = 200
        backend.stored = stored({"alpha": [server_page("alpha", i) for i in range(3)]})
        watcher.running = True  # the keep-running loop issues "catch-up" rescans
        await watcher.rescan(reason="catch-up")
        assert manifest.is_initialised()
        assert not watcher.catch_up.retry_due()
        assert not entry(manifest, page(library, "alpha", 0)).is_baseline
        assert queued_pages(watcher) == [f"gamma/gamma-p{i}.rm" for i in range(4)]

    @pytest.mark.parametrize("status", [429, 500])
    async def test_rate_limit_and_server_errors_do_not_initialise(self, watcher, manifest, backend, status):
        backend.stored_status = status
        await watcher.rescan(reason="start-up")
        assert not manifest.is_initialised() and not manifest.has_entries()

    async def test_sign_in_rejected_takes_the_sign_in_path(self, watcher, manifest, backend, mock_keychain):
        backend.stored_status = 401
        await watcher.rescan(reason="start-up")
        assert not manifest.is_initialised() and not manifest.has_entries()
        assert watcher.sync_queue.paused_reason == PAUSED_SIGN_IN
        assert watcher.cloud_sync.authenticated is False

    async def test_email_is_looked_up_when_unknown(self, watcher, cloud_sync, manifest, backend):
        cloud_sync.user_email = None
        backend.email = "Mixed.Case@Example.TEST"
        await watcher.rescan(reason="start-up")
        assert manifest.account() == "mixed.case@example.test"


class TestAccountBinding:
    async def test_other_account_on_same_host_resets_then_reconciles(
        self, watcher, cloud_sync, manifest, library, backend
    ):
        manifest.set_account("someone.else@example.test")
        manifest.mark_initialised()
        manifest.record_upload(page(library, "alpha", 0), fingerprint_file(page(library, "alpha", 0)))
        other = UploadManifest(manifest.db_path, "other.host")
        other.record_upload(page(library, "alpha", 0), fingerprint_file(page(library, "alpha", 0)))
        other.set_account("someone.else@example.test")

        await watcher.rescan(reason="reconnect")

        assert backend.stored_calls() == 1
        assert manifest.account() == EMAIL
        # Nothing on the server for this account: the selection uploads
        assert "alpha/alpha-p0.rm" in queued_pages(watcher)
        assert entry(manifest, page(library, "alpha", 0)) is None
        # Other hosts are not touched
        assert other.get(page(library, "alpha", 0)) is not None
        assert other.account() == "someone.else@example.test"

    async def test_entries_without_account_are_adopted(self, watcher, manifest, library, backend):
        manifest.mark_initialised()
        manifest.record_upload(page(library, "alpha", 0), fingerprint_file(page(library, "alpha", 0)))
        await watcher.rescan(reason="start-up")
        assert backend.calls == []
        assert manifest.account() == EMAIL
        assert not entry(manifest, page(library, "alpha", 0)).is_baseline

    async def test_initialised_host_same_account_makes_no_request(self, watcher, manifest, library, backend):
        manifest.set_account(EMAIL)
        manifest.mark_initialised()
        for _ in range(3):
            await watcher.rescan(reason="periodic")
        assert backend.calls == []
        assert watcher.catch_up.gate_open()

    async def test_server_switch_staging_to_production(self, config, cloud_sync, manifest, library, backend):
        """The original bug: only staging was ever synced; production gets everything it lacks."""
        config.api.url = STAGING
        staging = UploadManifest(manifest.db_path, config.api._keychain_user_id)
        staging.mark_initialised()
        staging.set_account(EMAIL)
        for nb, n in (("alpha", 3), ("beta", 2), ("gamma", 4)):
            for i in range(n):
                staging.record_upload(page(library, nb, i), fingerprint_file(page(library, nb, i)))
        # alpha-p2 edited while only staging was in use... and never synced anywhere
        page(library, "alpha", 2).write_bytes(b"edited later")

        config.api.url = PRODUCTION
        config.api._token = "prod-token"
        assert manifest.api_host != staging.api_host and not manifest.is_initialised()
        backend.stored = stored({
            "alpha": [server_page("alpha", 0), server_page("alpha", 1)],
            "gamma": [server_page("gamma", i) for i in range(4)],
        })

        # Matching size and mtime under staging: the file is not hashed again
        hashed = []
        real = catch_up_module.fingerprint_file

        def counting(path):
            hashed.append(Path(path).name)
            return real(path)

        watcher = FileWatcher(config, cloud_sync, manifest=manifest)
        with patch.object(catch_up_module, "fingerprint_file", counting):
            await watcher.rescan(reason="start-up")

        assert "rmirror.io/api/v1/sync/stored-pages" in backend.calls[-1]
        assert queued_pages(watcher) == ["alpha/alpha-p2.rm"]
        # No page was hashed again: matching size and mtime under staging, or (alpha-p2)
        # not on the server and left to upload. Only files staging never recorded are hashed.
        assert [name for name in hashed if name.endswith(".rm")] == []
        assert staging.get(page(library, "alpha", 2)).sha256 != fingerprint_file(page(library, "alpha", 2)).sha256
        assert manifest.get_meta("catch_up") == "done"


class TestWatcherLoop:
    async def test_start_catches_up_and_retries_on_its_own_backoff(self, config, cloud_sync, manifest, backend):
        from tests.unit.test_watcher_health import FakeObserver, FakeTime, wait_for

        fake_time = FakeTime()
        backend.stored_status = 503
        watcher = FileWatcher(
            config, cloud_sync, manifest=manifest,
            observer_factory=FakeObserver, clock=fake_time.clock, sleep=fake_time.sleep,
        )
        watcher.sync_queue.start = AsyncMock()
        watcher.sync_queue.stop = AsyncMock()
        task = asyncio.create_task(watcher.start())
        await wait_for(lambda: watcher.running)
        assert not manifest.is_initialised()
        assert watcher.last_rescan_result == "waiting for catch-up (cloud)"

        backend.stored_status = 200
        fake_time.advance(watcher.catch_up.FIRST_RETRY_SECONDS)  # well before the 60 s rescan
        await wait_for(manifest.is_initialised)
        await wait_for(lambda: watcher.last_rescan_reason == "catch-up")
        assert watcher.catch_up.gate_open()

        await watcher.stop()
        fake_time.advance(1)
        await asyncio.wait_for(task, timeout=5)


class TestFolderSwitchBeforeFirstContact:
    async def test_new_folder_is_not_baselined_before_the_catch_up(self, config, manifest, library):
        from app.main import Agent

        agent = Agent(config, agent_loop=MagicMock(), headless=True)
        file_watcher = MagicMock()
        file_watcher.sync_queue.manifest = manifest
        await agent._baseline_current_folder(file_watcher)
        assert not manifest.has_entries()


# ----------------------------------------------------------------------
# CloudSync.get_stored_pages
# ----------------------------------------------------------------------


class TestGetStoredPages:
    async def test_ok(self, cloud_sync, backend):
        backend.stored = stored({"alpha": [server_page("alpha", 0)]})
        data = await cloud_sync.get_stored_pages()
        parsed = parse_stored_pages(data)
        assert parsed.notebooks == {"alpha"}
        assert parsed.has_current("alpha", "alpha-p0", sha(page_bytes("alpha", 0)))

    @pytest.mark.parametrize("status, body", [(404, {"detail": "Not Found"}), (405, {"detail": "Method Not Allowed"})])
    async def test_missing_endpoint(self, cloud_sync, backend, status, body):
        backend.stored_status = status
        backend.stored_body = body
        with pytest.raises(StoredPagesUnavailableError):
            await cloud_sync.get_stored_pages()

    @pytest.mark.parametrize("body", [{"detail": "User not found"}, "<html>proxy</html>", {}])
    async def test_other_404_is_retryable(self, cloud_sync, backend, body):
        backend.stored_status = 404
        backend.stored_body = body
        with pytest.raises(CloudSyncError) as info:
            await cloud_sync.get_stored_pages()
        assert not isinstance(info.value, StoredPagesUnavailableError)
        assert info.value.transient is True

    @pytest.mark.parametrize("status, transient", [(429, True), (500, True), (503, True), (400, False)])
    async def test_errors(self, cloud_sync, backend, status, transient):
        backend.stored_status = status
        with pytest.raises(CloudSyncError) as info:
            await cloud_sync.get_stored_pages()
        assert info.value.transient is transient
        assert not isinstance(info.value, StoredPagesUnavailableError)

    async def test_401_after_recheck_signs_out(self, cloud_sync, backend, mock_keychain):
        backend.stored_status = 401
        with pytest.raises(AuthenticationRequiredError):
            await cloud_sync.get_stored_pages()
        assert cloud_sync.authenticated is False

    def test_malformed_response_is_rejected(self):
        for bad in ({}, {"notebooks": "x"}, {"notebooks": [{"pages": []}]}, {"notebooks": [{"notebook_uuid": "a", "pages": [{}]}]}):
            with pytest.raises(ValueError):
                parse_stored_pages(bad)


# ----------------------------------------------------------------------
# Local API: catch_up, first_sync, on_server, synced_pages, dismiss
# ----------------------------------------------------------------------


@pytest.fixture
def client(config, cloud_sync):
    loop = AgentLoop()
    loop.start()
    app = create_app(config, cloud_sync, agent=None, agent_loop=loop, app_token=TOKEN, headless=True)
    app.config["TESTING"] = True
    yield app.test_client()
    loop.stop()


def state(client) -> dict:
    return client.get("/api/v2/state", base_url=BASE_URL, headers=HEADERS).get_json()


def notebooks(client) -> dict:
    data = client.get("/api/v2/notebooks", base_url=BASE_URL, headers=HEADERS).get_json()
    return {nb["uuid"]: nb for nb in data["notebooks"]}


class TestLocalApi:
    def test_pending_while_signed_in_and_not_caught_up(self, client, manifest, library):
        manifest.record_upload(page(library, "alpha", 0), fingerprint_file(page(library, "alpha", 0)))
        data = state(client)
        assert data["catch_up"] == {"state": "pending", "unselected_on_server": 0}
        assert data["first_sync"]["completed"] is False  # never claimed while pending

    def test_pending_while_another_account_is_signed_in(self, client, manifest, library, cloud_sync):
        manifest.set_account("previous@example.test")
        manifest.mark_initialised()
        manifest.record_upload(page(library, "alpha", 0), fingerprint_file(page(library, "alpha", 0)))
        assert state(client)["catch_up"]["state"] == "pending"
        assert state(client)["first_sync"]["completed"] is False
        cloud_sync.user_email = "previous@example.test"
        assert state(client)["catch_up"]["state"] == "not_needed"
        assert state(client)["first_sync"]["completed"] is True

    async def test_server_has_everything_completes_first_sync(self, client, watcher, backend):
        backend.stored = stored({
            "alpha": [server_page("alpha", i) for i in range(3)],
            "gamma": [server_page("gamma", i) for i in range(4)],
        })
        await watcher.rescan(reason="start-up")
        data = state(client)
        assert data["catch_up"] == {"state": "done", "unselected_on_server": 0}
        assert data["first_sync"]["completed"] is True

    async def test_nothing_on_server_is_not_completed(self, client, watcher):
        await watcher.rescan(reason="start-up")
        data = state(client)
        assert data["catch_up"]["state"] == "done"
        assert data["first_sync"]["completed"] is False

    async def test_unselected_on_server_notice_and_dismiss(self, client, watcher, config, backend):
        backend.stored = stored({"beta": [server_page("beta", 0), server_page("beta", 1, b"old")]})
        await watcher.rescan(reason="start-up")

        nbs = notebooks(client)
        assert nbs["beta"]["on_server"] is True and nbs["alpha"]["on_server"] is False
        assert state(client)["catch_up"] == {"state": "done", "unselected_on_server": 1}

        resp = client.post("/api/v2/catch-up/dismiss", base_url=BASE_URL, headers=HEADERS)
        assert resp.status_code == 200 and resp.get_json() == {"ok": True}
        assert state(client)["catch_up"]["unselected_on_server"] == 0
        config.sync.selected_notebooks = ["gamma"]  # untick more later: still not nagged
        assert state(client)["catch_up"]["unselected_on_server"] == 0

    async def test_notice_clears_itself_when_the_notebook_is_selected(self, client, watcher, config, backend, manifest):
        backend.stored = stored({"beta": [server_page("beta", 0)]})
        await watcher.rescan(reason="start-up")
        config.sync.selected_notebooks = ["alpha", "gamma", "beta"]
        assert state(client)["catch_up"]["unselected_on_server"] == 0
        config.sync.selected_notebooks = ["alpha", "gamma"]
        assert state(client)["catch_up"]["unselected_on_server"] == 0
        assert manifest.get_meta("selection_notice") == "cleared"

    def test_dismiss_needs_the_app_token(self, client):
        resp = client.post("/api/v2/catch-up/dismiss", base_url=BASE_URL)
        assert resp.status_code == 401

    async def test_page_counts_after_catch_up(self, client, watcher, config, backend, manifest):
        """On-server unselected notebook and a selected one with changed pages: no double counting."""
        backend.stored = stored({
            "beta": [server_page("beta", 0), server_page("beta", 1, b"old")],
            "gamma": [server_page("gamma", 0), server_page("gamma", 1, b"old"), server_page("gamma", 2)],
        })
        await watcher.rescan(reason="start-up")

        nbs = notebooks(client)
        assert (nbs["beta"]["page_count"], nbs["beta"]["synced_pages"]) == (2, 1)
        assert (nbs["gamma"]["page_count"], nbs["gamma"]["synced_pages"]) == (4, 2)

        planner = PagePlanner(config, manifest)
        # gamma: p1 (changed) and p3 (missing) are still to upload; beta: only p1
        assert planner.count_pages_to_upload(["gamma"]) == 2
        assert planner.count_pages_to_upload(["beta"]) == 1

    async def test_synced_pages_never_exceed_page_count(self, client, watcher, config, backend):
        config.sync.max_pages_per_notebook = 2
        backend.stored = stored({"beta": [server_page("beta", i) for i in range(2)],
                                 "gamma": [server_page("gamma", i) for i in range(4)]})
        await watcher.rescan(reason="start-up")
        nbs = notebooks(client)
        assert (nbs["gamma"]["page_count"], nbs["gamma"]["synced_pages"]) == (2, 2)


class TestQueueUnaffected:
    async def test_existing_401_pause_path_unchanged(self, config, manifest):
        """A sign-in rejected during uploads still pauses the queue and keeps its items."""
        cloud_sync = MagicMock()
        cloud_sync.upload_file = AsyncMock(side_effect=AuthenticationRequiredError("x", status_code=401))
        manifest.mark_initialised()
        watcher = FileWatcher(config, cloud_sync, manifest=manifest)
        watcher.sync_queue.metadata_sync = MagicMock(run=AsyncMock())
        await watcher.rescan(reason="start-up")
        watcher.sync_queue._flush_due = lambda: 0
        for key, (item, _seen) in list(watcher.sync_queue._pending.items()):
            watcher.sync_queue.queue.put_nowait(item)
        await watcher.sync_queue._run_once()
        assert watcher.sync_queue.paused_reason == PAUSED_SIGN_IN


# ----------------------------------------------------------------------
# Review follow-ups
# ----------------------------------------------------------------------


def clocked_watcher(config, cloud_sync, manifest, now):
    return FileWatcher(config, cloud_sync, manifest=manifest, clock=lambda: now[0])


class TestFallbacks:
    async def test_long_network_failure_falls_back_to_unavailable(self, config, cloud_sync, manifest, backend):
        now = [1000.0]
        watcher = clocked_watcher(config, cloud_sync, manifest, now)
        backend.stored_status = 503
        await watcher.rescan(reason="start-up")
        assert not manifest.is_initialised()
        now[0] += watcher.catch_up.GIVE_UP_SECONDS - 1
        await watcher.rescan(reason="reconnect")
        assert not manifest.is_initialised()
        now[0] += 1
        await watcher.rescan(reason="reconnect")
        assert manifest.get_meta("catch_up") == "unavailable"
        assert not watcher.catch_up.retry_due()

    @pytest.mark.parametrize("status", [400, 403])
    async def test_other_client_errors_fall_back_immediately(self, watcher, manifest, backend, status):
        backend.stored_status = status
        await watcher.rescan(reason="start-up")
        assert manifest.get_meta("catch_up") == "unavailable"

    @pytest.mark.parametrize("answer", ["not json", {"pages": []}, {"notebooks": [{"pages": []}]}])
    async def test_malformed_answer_falls_back_immediately(self, watcher, manifest, backend, answer):
        backend.stored = answer
        await watcher.rescan(reason="start-up")
        assert manifest.get_meta("catch_up") == "unavailable"

    async def test_non_fastapi_404_is_retried(self, watcher, manifest, backend):
        backend.stored_status = 404
        backend.stored_body = {"detail": "User not found"}
        await watcher.rescan(reason="start-up")
        assert not manifest.is_initialised() and not manifest.has_entries()


class TestUpgradeAfterFallback:
    async def test_next_start_upgrades_unavailable_to_done(self, config, cloud_sync, manifest, library, backend):
        backend.stored_status = 404
        backend.stored_body = {"detail": "Not Found"}
        first = FileWatcher(config, cloud_sync, manifest=manifest)
        await first.rescan(reason="start-up")
        assert manifest.get_meta("catch_up") == "unavailable"
        assert entry(manifest, page(library, "beta", 0)).is_baseline
        uploaded_before = manifest.uploaded_paths()

        # Next start: the backend has the endpoint now
        backend.stored_status = 200
        backend.stored = stored({
            "beta": [server_page("beta", 0), server_page("beta", 1, b"older")],
            "alpha": [server_page("alpha", 0)],
        })
        second = FileWatcher(config, cloud_sync, manifest=manifest)
        await second.rescan(reason="start-up")
        assert backend.stored_calls() == 2
        assert manifest.get_meta("catch_up") == "done"
        assert not entry(manifest, page(library, "beta", 0)).is_baseline  # upgraded
        assert entry(manifest, page(library, "beta", 1)).is_baseline  # differs: kept
        assert not entry(manifest, page(library, "alpha", 0)).is_baseline  # unrecorded -> uploaded
        assert uploaded_before <= manifest.uploaded_paths()  # nothing removed
        assert manifest.server_notebooks() == {"alpha", "beta"}
        assert manifest.get_meta("selection_notice") == "pending"  # beta is not selected
        assert manifest.last_upload_at() is None  # catch-up records are not uploads
        # The upgrade itself queues nothing new (alpha-p0 no longer counts as changed)
        second.sync_queue._pending.clear()
        await second.rescan(reason="periodic")
        assert "alpha/alpha-p0.rm" not in queued(second)
        assert backend.stored_calls() == 2  # once per start, not per rescan

    async def test_failed_upgrade_keeps_unavailable_and_is_not_retried_per_rescan(
        self, config, cloud_sync, manifest, backend
    ):
        manifest.set_account(EMAIL)
        manifest.mark_initialised()
        manifest.set_meta("catch_up", "unavailable")
        backend.stored_status = 503
        watcher = FileWatcher(config, cloud_sync, manifest=manifest)
        await watcher.rescan(reason="start-up")
        await watcher.rescan(reason="periodic")
        assert backend.stored_calls() == 1
        assert manifest.get_meta("catch_up") == "unavailable"


class TestPageLimitFollowsServer:
    async def test_beyond_limit_page_held_in_another_version_is_uploaded(self, watcher, config, manifest, library, backend):
        config.sync.max_pages_per_notebook = 2
        config.sync.selected_notebooks = ["gamma"]
        backend.stored = stored({"gamma": [server_page("gamma", 0, b"older"), server_page("gamma", 2), server_page("gamma", 3)]})
        await watcher.rescan(reason="start-up")
        # p0 is beyond the limit but the server holds another version: follows the file
        assert queued_pages(watcher) == ["gamma/gamma-p0.rm"]
        # p1 beyond the limit, not on the server: baselined
        assert entry(manifest, page(library, "gamma", 1)).is_baseline


class TestRetryLoop:
    async def test_sign_in_rejected_does_not_leave_a_retry_due(self, config, cloud_sync, manifest, backend, mock_keychain):
        now = [1000.0]
        watcher = clocked_watcher(config, cloud_sync, manifest, now)
        backend.stored_status = 503
        await watcher.rescan(reason="start-up")
        backend.stored_status = 401
        now[0] += 10
        assert watcher.catch_up.retry_due()
        await watcher.rescan(reason="catch-up")
        now[0] += 1000
        assert not watcher.catch_up.retry_due()

    async def test_signed_out_clears_the_retry(self, config, cloud_sync, manifest, backend):
        now = [1000.0]
        watcher = clocked_watcher(config, cloud_sync, manifest, now)
        backend.stored_status = 503
        await watcher.rescan(reason="start-up")
        cloud_sync.authenticated = False
        now[0] += 10
        await watcher.rescan(reason="catch-up")
        now[0] += 1000
        assert not watcher.catch_up.retry_due()

    async def test_host_change_during_request_clears_the_retry(self, config, cloud_sync, manifest, backend):
        now = [1000.0]
        watcher = clocked_watcher(config, cloud_sync, manifest, now)
        backend.stored_status = 503
        await watcher.rescan(reason="start-up")
        backend.stored_status = 200
        real = cloud_sync.get_stored_pages

        async def switch_then_answer():
            config.api.url = STAGING
            return await real()

        cloud_sync.get_stored_pages = switch_then_answer
        now[0] += 10
        await watcher.rescan(reason="catch-up")
        now[0] += 1000
        assert not watcher.catch_up.retry_due()

    async def test_no_rescan_every_second_after_sign_in_is_rejected(
        self, config, cloud_sync, manifest, backend, mock_keychain
    ):
        from tests.unit.test_watcher_health import FakeObserver, FakeTime, wait_for

        fake_time = FakeTime()
        backend.stored_status = 503
        watcher = FileWatcher(
            config, cloud_sync, manifest=manifest,
            observer_factory=FakeObserver, clock=fake_time.clock, sleep=fake_time.sleep,
        )
        watcher.sync_queue.start = AsyncMock()
        watcher.sync_queue.stop = AsyncMock()
        task = asyncio.create_task(watcher.start())
        await wait_for(lambda: watcher.running)
        backend.stored_status = 401
        fake_time.advance(watcher.catch_up.FIRST_RETRY_SECONDS)
        await wait_for(lambda: watcher.catch_up.waiting_reason == "sign_in")
        calls = backend.stored_calls()
        for _ in range(20):  # 20 s, below the 60 s rescan interval
            fake_time.advance(1)
            await asyncio.sleep(0.005)
        assert backend.stored_calls() == calls
        await watcher.stop()
        fake_time.advance(1)
        await asyncio.wait_for(task, timeout=5)


class TestRobustness:
    async def test_event_during_retry_is_not_lost(self, config, cloud_sync, manifest, library, backend):
        now = [1000.0]
        watcher = clocked_watcher(config, cloud_sync, manifest, now)
        handler = ReMarkableEventHandler(watcher.sync_queue, config, gate=watcher.catch_up.gate_open)
        backend.stored_status = 503
        backend.stored = stored({"alpha": [server_page("alpha", i) for i in range(3)]})
        await watcher.rescan(reason="start-up")

        # While retrying: the user edits a page the server has; the event is not queued
        page(library, "alpha", 1).write_bytes(b"edited while the catch-up was retrying")
        handler.dispatch(FileModifiedEvent(str(page(library, "alpha", 1))))
        assert queued(watcher) == []

        backend.stored_status = 200
        now[0] += 10
        await watcher.rescan(reason="reconnect")
        assert "alpha/alpha-p1.rm" in queued_pages(watcher)
        assert entry(manifest, page(library, "alpha", 1)) is None

    async def test_process_death_between_reset_and_reconcile(self, config, cloud_sync, manifest, library, backend):
        manifest.set_account("previous@example.test")
        manifest.mark_initialised()
        manifest.record_upload(page(library, "alpha", 0), fingerprint_file(page(library, "alpha", 0)))
        backend.stored_status = 503  # the reconcile does not happen in this run
        await FileWatcher(config, cloud_sync, manifest=manifest).rescan(reason="start-up")
        assert not manifest.is_initialised() and not manifest.has_entries()

        # "Restart": a new watcher reconciles for the new account
        backend.stored_status = 200
        backend.stored = stored({"alpha": [server_page("alpha", 0)]})
        await FileWatcher(config, cloud_sync, manifest=manifest).rescan(reason="start-up")
        assert manifest.account() == EMAIL
        assert not entry(manifest, page(library, "alpha", 0)).is_baseline


class TestSignInStartsCatchUp:
    async def test_reauthenticate_rescans_a_running_watcher(self, config):
        from app.main import Agent

        agent = Agent(config, agent_loop=MagicMock(), headless=True)
        agent.running = True
        agent.cloud_sync = MagicMock(authenticate=AsyncMock())
        agent._request_watcher_start = MagicMock(return_value=False)  # already running
        agent.file_watcher = MagicMock(running=True, _rescan_logged=AsyncMock())
        with patch.object(agent, "_maybe_refresh_account"):
            assert await agent.reauthenticate() is True
        await asyncio.sleep(0)
        agent.file_watcher._rescan_logged.assert_awaited_once_with("sign-in")


class TestApiFollowUps:
    async def test_notice_survives_a_missing_folder(self, client, watcher, config, backend, manifest, tmp_path):
        backend.stored = stored({"beta": [server_page("beta", 0)]})
        await watcher.rescan(reason="start-up")
        source = config.remarkable.source_directory
        config.remarkable.source_directory = str(tmp_path / "unplugged")
        assert state(client)["catch_up"]["unselected_on_server"] == 0
        assert manifest.get_meta("selection_notice") == "pending"
        config.remarkable.source_directory = source
        assert state(client)["catch_up"]["unselected_on_server"] == 1

    async def test_catch_up_records_are_not_uploads(self, client, watcher, manifest, library, backend):
        backend.stored = stored({"alpha": [server_page("alpha", i) for i in range(3)]})
        await watcher.rescan(reason="start-up")
        data = state(client)
        assert data["last_upload_at"] is None
        assert data["first_sync"]["completed"] is True
        manifest.record_upload(page(library, "gamma", 0), fingerprint_file(page(library, "gamma", 0)))
        assert state(client)["last_upload_at"] is not None

    async def test_first_sync_counts_pages_only(self, client, watcher, manifest, library):
        await watcher.rescan(reason="start-up")  # nothing on the server
        meta = library / "alpha.metadata"
        manifest.record_upload(meta, fingerprint_file(meta))
        assert state(client)["first_sync"]["completed"] is False
        manifest.record_upload(page(library, "alpha", 0), fingerprint_file(page(library, "alpha", 0)))
        assert state(client)["first_sync"]["completed"] is True

    async def test_notebook_list_reads_page_order_once_and_quietly(self, client, watcher, manifest, library, caplog):
        import logging

        (library / "alpha" / "orphan.rm").write_bytes(b"page not in .content")
        manifest.mark_initialised()
        manifest.record_upload(page(library, "alpha", 0), fingerprint_file(page(library, "alpha", 0)))
        with patch.object(PagePlanner, "_limit_pages", autospec=True, side_effect=PagePlanner._limit_pages) as spy:
            with caplog.at_level(logging.INFO):
                first = notebooks(client)
                second = notebooks(client)
        assert first == second
        calls = spy.call_count
        assert calls <= 3  # one per notebook with pages, on the first request only
        assert "orphaned" not in caplog.text
        (library / "alpha" / "alpha-p9.rm").write_bytes(b"new page")
        with patch.object(PagePlanner, "_limit_pages", autospec=True, side_effect=PagePlanner._limit_pages) as spy:
            notebooks(client)
        assert spy.call_count == 1  # only the changed notebook
