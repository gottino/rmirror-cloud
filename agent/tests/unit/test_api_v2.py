"""
Local API v2 (docs/local-api.md): token enforcement, error codes and response shapes.
"""

import asyncio
import contextlib
import json
import os
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.agent_loop import AgentLoop
from app.config import Config
from app.sync.cloud_sync import CloudSync
from app.sync.manifest import UploadManifest, fingerprint_file
from app.sync.queue import PAUSED_QUOTA, PAUSED_SIGN_IN, WAITING_OFFLINE, WAITING_RATE_LIMITED
from app.sync.quota_cache import QuotaCache
from app.web import routes
from app.web.app import create_app
from app.web.shared import InitialSyncJob

PORT = 5556  # matches test_config
BASE_URL = f"http://127.0.0.1:{PORT}"
TOKEN = "a" * 64
HEADERS = {"X-RMirror-App-Token": TOKEN}


# ----------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------


class Backend:
    """httpx MockTransport handler for the cloud API."""

    def __init__(self):
        self.quota = {"used": 4, "limit": 200, "reset_at": "2026-12-01T00:00:00"}
        self.deleted = [
            {"notebook_uuid": "gone-1", "visible_name": "Old notes", "deleted_at": "2026-11-01T10:00:00"}
        ]
        self.calls: list[str] = []
        self.status = 200

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        self.calls.append(f"{request.method} {path}")
        if self.status != 200:
            return httpx.Response(self.status, json={})
        if path.endswith("/quota/status"):
            return httpx.Response(200, json=self.quota)
        if path.endswith("/sync/deleted-notebooks"):
            return httpx.Response(200, json={"deleted_notebooks": self.deleted})
        if path.endswith("/acknowledge"):
            return httpx.Response(200, json={"success": True})
        if path.endswith("/users/me"):
            return httpx.Response(200, json={"id": 1, "email": "user@example.test"})
        return httpx.Response(200, json={})


def _write_notebook(root: Path, uuid: str, name: str, *, parent: str = "", pages: int = 2,
                    last_opened: int | None = 1_700_000_000_000, last_modified: int = 1_690_000_000_000,
                    doc_type: str = "DocumentType", deleted: bool = False, rm_files: bool = True) -> None:
    meta = {"visibleName": name, "type": doc_type, "parent": parent, "lastModified": str(last_modified)}
    if last_opened is not None:
        meta["lastOpened"] = str(last_opened)
    if deleted:
        meta["deleted"] = True
    (root / f"{uuid}.metadata").write_text(json.dumps(meta))
    if doc_type == "DocumentType":
        page_ids = [f"{uuid}-p{i}" for i in range(pages)]
        (root / f"{uuid}.content").write_text(json.dumps({"pages": page_ids}))
        if rm_files:
            (root / uuid).mkdir(exist_ok=True)
            for pid in page_ids:
                (root / uuid / f"{pid}.rm").write_bytes(pid.encode())


@pytest.fixture
def library(tmp_path) -> Path:
    root = tmp_path / "desktop"
    root.mkdir()
    _write_notebook(root, "work", "Work", doc_type="CollectionType")
    _write_notebook(root, "y2026", "2026", parent="work", doc_type="CollectionType")
    _write_notebook(root, "meeting", "Meeting Notes", parent="y2026", pages=3, last_opened=1_763_000_000_000)
    _write_notebook(root, "diary", "Diary", pages=5, last_opened=1_762_000_000_000)
    _write_notebook(root, "big", "Big", pages=50, last_opened=1_764_000_000_000)
    _write_notebook(root, "trashed", "Trashed", parent="trash", pages=1)
    _write_notebook(root, "book", "Book", pages=1)
    (root / "book.pdf").write_bytes(b"%PDF")
    return root


@pytest.fixture
def save_mock():
    with patch.object(Config, "save", autospec=True) as save:
        yield save


@pytest.fixture
def config(test_config_with_token, save_mock, library):
    test_config_with_token.remarkable.source_directory = str(library)
    test_config_with_token.sync.sync_all_notebooks = False
    return test_config_with_token


@pytest.fixture
def backend():
    return Backend()


@pytest.fixture
def cloud_sync(config, backend):
    sync = CloudSync(config)
    sync.client = httpx.AsyncClient(transport=httpx.MockTransport(backend))
    sync.authenticated = True
    return sync


@pytest.fixture
def agent_loop():
    loop = AgentLoop()
    loop.start()
    yield loop
    loop.stop()


class FakeAgent:
    """The parts of app.main.Agent that the v2 routes use."""

    def __init__(self, config):
        self.config = config
        self.headless = True
        self.quota_cache = QuotaCache()
        self.watcher_state = "running"
        self.file_watcher = None
        self.stopped_watcher = False
        self.started_watcher = 0
        self.reauthenticated = 0
        self.auth_state = "signed_in"
        self.folder_changes: list[str] = []

    async def change_source_directory(self, new_directory):
        self.folder_changes.append(new_directory)
        self.config.remarkable.source_directory = new_directory
        return "ok"

    async def stop_file_watcher(self):
        self.stopped_watcher = True
        self.file_watcher = None

    def update_folder_flags(self):
        from app.remarkable.library import folder_state

        return folder_state(self.config.remarkable.source_directory)

    def start_file_watcher_sync(self):
        self.started_watcher += 1
        return True

    async def reauthenticate(self):
        self.reauthenticated += 1
        return True

    def request_account_refresh(self):
        pass


@pytest.fixture
def agent(config):
    return FakeAgent(config)


@pytest.fixture
def app(config, cloud_sync, agent_loop, agent):
    flask_app = create_app(config, cloud_sync, agent=agent, agent_loop=agent_loop, app_token=TOKEN, headless=True)
    flask_app.config["TESTING"] = True
    return flask_app


@pytest.fixture
def client(app):
    return app.test_client()


def get(client, path, **kw):
    return client.get(path, base_url=BASE_URL, headers=kw.pop("headers", HEADERS), **kw)


def post(client, path, body=None, **kw):
    return client.post(path, base_url=BASE_URL, headers=kw.pop("headers", HEADERS), json=body, **kw)


def put(client, path, body=None, **kw):
    return client.put(path, base_url=BASE_URL, headers=kw.pop("headers", HEADERS), json=body, **kw)


def error_code(resp) -> str:
    return resp.get_json()["error"]["code"]


# ----------------------------------------------------------------------
# Token and request rules
# ----------------------------------------------------------------------


class TestAppToken:
    @pytest.mark.parametrize(
        "path", ["/api/v2/state", "/api/v2/notebooks", "/api/v2/settings", "/api/v2/sync/progress"]
    )
    def test_missing_token_is_rejected(self, client, path):
        resp = get(client, path, headers={})
        assert resp.status_code == 401
        assert error_code(resp) == "bad_app_token"

    def test_wrong_token_is_rejected(self, client):
        resp = get(client, "/api/v2/state", headers={"X-RMirror-App-Token": "b" * 64})
        assert resp.status_code == 401
        assert error_code(resp) == "bad_app_token"

    def test_token_is_compared_in_constant_time(self, client):
        with patch("app.web.shared.hmac.compare_digest", return_value=False) as compare:
            resp = get(client, "/api/v2/state")
        assert resp.status_code == 401
        compare.assert_called_once()

    def test_post_without_token_is_rejected_before_acting(self, client, cloud_sync):
        resp = post(client, "/api/v2/auth/sign-out", headers={})
        assert resp.status_code == 401
        assert cloud_sync.authenticated is True

    def test_right_token_is_accepted(self, client):
        assert get(client, "/api/v2/state").status_code == 200

    def test_health_needs_no_token(self, client):
        assert client.get("/health", base_url=BASE_URL).status_code == 200

    @pytest.mark.parametrize(
        "method, path",
        [
            ("GET", "/"),
            ("GET", "/api/status"),
            ("POST", "/api/config"),
            ("GET", "/api/config"),
            ("POST", "/api/sync/initial"),
            ("POST", "/api/notebooks/selection"),
            ("POST", "/api/auth/environment"),
            ("POST", "/api/auth/logout"),
            ("GET", "/updates"),
            ("GET", "/static/rm-icon.png"),
        ],
    )
    def test_legacy_routes_do_not_exist_in_headless_mode(self, client, config, save_mock, method, path):
        url_before = config.api.url
        resp = client.open(path, method=method, base_url=BASE_URL, json={"api": {"url": "http://evil"}})
        assert resp.status_code == 404
        assert config.api.url == url_before
        save_mock.assert_not_called()

    def test_legacy_routes_still_exist_in_legacy_mode(self, config, cloud_sync, agent_loop):
        app = create_app(config, cloud_sync, agent=None, agent_loop=agent_loop)
        legacy = app.test_client()
        assert legacy.get("/api/status", base_url=BASE_URL).status_code == 200
        assert legacy.get("/", base_url=BASE_URL).status_code == 200
        assert legacy.get("/auth/done", base_url=BASE_URL).status_code == 404

    @pytest.mark.parametrize("method", ["GET", "POST", "DELETE"])
    def test_unknown_v2_path_without_token_is_401(self, client, method):
        resp = client.open("/api/v2/does-not-exist", method=method, base_url=BASE_URL)
        assert resp.status_code == 401 and error_code(resp) == "bad_app_token"

    def test_wrong_method_without_token_is_401(self, client):
        resp = client.delete("/api/v2/state", base_url=BASE_URL)
        assert resp.status_code == 401 and error_code(resp) == "bad_app_token"

    def test_ipv6_loopback_host_is_allowed_in_headless_mode(self, client, config, cloud_sync, agent_loop):
        resp = client.get("/health", base_url=f"http://[::1]:{PORT}")
        assert resp.status_code == 200
        legacy = create_app(config, cloud_sync, agent=None, agent_loop=agent_loop).test_client()
        assert legacy.get("/health", base_url=f"http://[::1]:{PORT}").status_code == 403

    def test_no_token_configured_leaves_v2_open(self, config, cloud_sync, agent_loop):
        app = create_app(config, cloud_sync, agent=None, agent_loop=agent_loop)
        assert app.test_client().get("/api/v2/state", base_url=BASE_URL).status_code == 200

    def test_host_check_still_applies(self, client):
        resp = client.get("/api/v2/state", base_url=f"http://evil.example:{PORT}", headers=HEADERS)
        assert resp.status_code == 403

    def test_unknown_v2_path_answers_json(self, client):
        resp = get(client, "/api/v2/nope")
        assert resp.status_code == 404
        assert error_code(resp) == "invalid_request"

    def test_wrong_method_answers_json(self, client):
        resp = client.delete("/api/v2/state", base_url=BASE_URL, headers=HEADERS)
        assert resp.status_code == 405
        assert error_code(resp) == "invalid_request"

    def test_legacy_404_is_unchanged(self, client):
        resp = client.get("/nope", base_url=BASE_URL)
        assert resp.status_code == 404
        assert resp.get_json(silent=True) is None


# ----------------------------------------------------------------------
# GET /api/v2/state
# ----------------------------------------------------------------------


class TestState:
    def test_shape(self, client, config):
        data = get(client, "/api/v2/state").get_json()
        assert set(data) == {
            "api_version", "core_version", "auth", "environment", "folder", "watcher", "queue",
            "quota", "first_sync", "sync", "last_upload_at",
        }
        assert data["api_version"] == 2
        assert data["auth"] == {"state": "signed_in", "signed_in": True, "email": None, "sign_in_required": False}
        assert data["environment"] == {
            "name": "custom",
            "api_url": config.api.url,
            "dashboard_url": "http://test-api.rmirror.io",
        }
        assert data["folder"] == {"path": config.remarkable.source_directory, "state": "ok"}
        assert data["watcher"] == {
            "state": "running", "observer_alive": False, "last_event_at": None, "last_rescan_at": None,
        }
        assert data["queue"] == {"pending": 0, "running": False, "paused_reason": None}
        assert data["quota"] is None
        assert data["first_sync"] == {"completed": False}
        assert data["sync"]["state"] == "idle"
        assert data["last_upload_at"] is None

    def test_no_cloud_round_trip(self, client, backend):
        for _ in range(3):
            get(client, "/api/v2/state")
        assert backend.calls == []

    def test_quota_from_cache(self, client, agent):
        agent.quota_cache.store({"used": 4, "limit": 200, "reset_at": "2026-12-01T00:00:00"})
        quota = get(client, "/api/v2/state").get_json()["quota"]
        assert quota["used"] == 4 and quota["limit"] == 200 and quota["remaining"] == 196
        assert quota["reset_at"] == "2026-12-01T00:00:00Z"
        assert quota["fetched_at"].endswith("Z")

    def test_unlimited_quota(self, client, agent):
        agent.quota_cache.store({"used": 40, "limit": -1})
        quota = get(client, "/api/v2/state").get_json()["quota"]
        assert quota["limit"] == -1 and quota["remaining"] is None

    def test_signed_out(self, client, cloud_sync, agent):
        agent.quota_cache.store({"used": 4, "limit": 200})
        cloud_sync.authenticated = False
        data = get(client, "/api/v2/state").get_json()
        assert data["auth"]["signed_in"] is False
        assert data["auth"]["sign_in_required"] is False
        assert data["quota"] is None

    def test_rejected_sign_in_requires_sign_in(self, client, cloud_sync):
        cloud_sync.authenticated = False
        cloud_sync.sign_in_rejected = True
        assert get(client, "/api/v2/state").get_json()["auth"]["sign_in_required"] is True

    def test_email_when_known(self, client, cloud_sync):
        cloud_sync.user_email = "user@example.test"
        assert get(client, "/api/v2/state").get_json()["auth"]["email"] == "user@example.test"

    def test_production_environment(self, client, config):
        config.api.url = "https://rmirror.io/api/v1"
        env = get(client, "/api/v2/state").get_json()["environment"]
        assert env == {"name": "production", "api_url": "https://rmirror.io/api/v1", "dashboard_url": "https://rmirror.io"}

    def test_missing_folder(self, client, config, tmp_path):
        config.remarkable.source_directory = str(tmp_path / "nowhere")
        assert get(client, "/api/v2/state").get_json()["folder"]["state"] == "missing"

    @pytest.mark.skipif(os.geteuid() == 0, reason="root can list any folder")
    def test_unreadable_folder_is_rechecked_on_every_call(self, client, config, library):
        os.chmod(library, 0)
        try:
            assert get(client, "/api/v2/state").get_json()["folder"]["state"] == "unreadable"
        finally:
            os.chmod(library, 0o755)
        assert get(client, "/api/v2/state").get_json()["folder"]["state"] == "ok"

    def test_first_sync_from_manifest(self, client, config, library):
        assert get(client, "/api/v2/state").get_json()["first_sync"]["completed"] is False
        manifest = UploadManifest.for_config(config)
        page = next((library / "meeting").glob("*.rm"))
        manifest.record_baseline(page, fingerprint_file(page))
        assert get(client, "/api/v2/state").get_json()["first_sync"]["completed"] is False
        manifest.record_upload(page, fingerprint_file(page))
        data = get(client, "/api/v2/state").get_json()
        assert data["first_sync"]["completed"] is True
        assert data["last_upload_at"].endswith("Z")

    def test_first_sync_is_per_api_host(self, client, config, library):
        page = next((library / "meeting").glob("*.rm"))
        UploadManifest(UploadManifest.for_config(config).db_path, "other.host").record_upload(
            page, fingerprint_file(page)
        )
        assert get(client, "/api/v2/state").get_json()["first_sync"]["completed"] is False

    @pytest.mark.parametrize(
        "paused, waiting, expected",
        [
            (PAUSED_SIGN_IN, None, "sign_in"),
            (PAUSED_QUOTA, None, "quota"),
            (None, WAITING_RATE_LIMITED, "rate_limited"),
            (None, WAITING_OFFLINE, "offline"),
            (None, None, None),
        ],
    )
    def test_queue_paused_reason(self, client, agent, paused, waiting, expected):
        queue = MagicMock()
        queue.get_stats.return_value = {"queue_size": 2, "pending": 1, "running": True, "paused_reason": paused}
        queue.waiting_reason = waiting
        agent.file_watcher = SimpleNamespace(sync_queue=queue, get_health=lambda: {
            "observer_alive": True, "last_event_at": None, "last_rescan_at": "2026-11-23T09:00:00",
        })
        data = get(client, "/api/v2/state").get_json()
        assert data["queue"] == {"pending": 3, "running": True, "paused_reason": expected}
        assert data["auth"]["sign_in_required"] is (expected == "sign_in")
        assert data["watcher"]["observer_alive"] is True
        assert data["watcher"]["last_rescan_at"].endswith("Z")


# ----------------------------------------------------------------------
# Notebooks and selection
# ----------------------------------------------------------------------


class TestNotebooks:
    def test_flat_list_of_documents(self, client, config, library):
        data = get(client, "/api/v2/notebooks").get_json()
        assert data["folder_state"] == "ok"
        assert data["sync_all"] is False
        by_uuid = {nb["uuid"]: nb for nb in data["notebooks"]}
        # No folders, no trash, no PDFs
        assert set(by_uuid) == {"meeting", "diary", "big"}
        meeting = by_uuid["meeting"]
        assert meeting["name"] == "Meeting Notes"
        assert meeting["folder_path"] == ["Work", "2026"]
        assert meeting["document_type"] == "notebook"
        assert meeting["page_count"] == 3
        assert meeting["last_opened_at"].endswith("Z")
        assert meeting["last_modified_at"].endswith("Z")
        assert meeting["selected"] is False
        assert meeting["synced_pages"] == 0

    def test_selected_and_synced_pages(self, client, config, library):
        config.sync.selected_notebooks = ["diary"]
        manifest = UploadManifest.for_config(config)
        for page in list((library / "diary").glob("*.rm"))[:2]:
            manifest.record_upload(page, fingerprint_file(page))
        by_uuid = {nb["uuid"]: nb for nb in get(client, "/api/v2/notebooks").get_json()["notebooks"]}
        assert by_uuid["diary"]["selected"] is True
        assert by_uuid["diary"]["synced_pages"] == 2
        assert by_uuid["big"]["selected"] is False

    def test_sync_all_selects_everything_and_excluded_are_left_out(self, client, config):
        config.sync.sync_all_notebooks = True
        config.sync.excluded_notebooks = ["big"]
        by_uuid = {nb["uuid"]: nb for nb in get(client, "/api/v2/notebooks").get_json()["notebooks"]}
        assert by_uuid["diary"]["selected"] is True
        assert "big" not in by_uuid

    def test_page_count_is_what_a_sync_uploads(self, client, config, library):
        # An orphan .rm file (not in .content) is uploaded too, so it counts
        (library / "diary" / "orphan.rm").write_bytes(b"x")
        by_uuid = {nb["uuid"]: nb for nb in get(client, "/api/v2/notebooks").get_json()["notebooks"]}
        assert by_uuid["diary"]["page_count"] == 6
        config.sync.max_pages_per_notebook = 4
        by_uuid = {nb["uuid"]: nb for nb in get(client, "/api/v2/notebooks").get_json()["notebooks"]}
        assert by_uuid["diary"]["page_count"] == 4
        assert by_uuid["meeting"]["page_count"] == 3

    def test_missing_folder(self, client, config, tmp_path):
        config.remarkable.source_directory = str(tmp_path / "nowhere")
        data = get(client, "/api/v2/notebooks").get_json()
        assert data == {"folder_state": "missing", "sync_all": False, "notebooks": []}

    def test_put_selection(self, client, config, save_mock):
        resp = put(client, "/api/v2/selection", {"sync_all": False, "selected_notebooks": ["diary", "meeting"]})
        assert resp.status_code == 200 and resp.get_json() == {"ok": True}
        assert config.sync.sync_all_notebooks is False
        assert config.sync.selected_notebooks == ["diary", "meeting"]
        save_mock.assert_called_once()

    @pytest.mark.parametrize(
        "body",
        [None, [], {}, {"sync_all": "yes"}, {"selected_notebooks": "diary"}, {"selected_notebooks": [1]}],
    )
    def test_put_selection_invalid(self, client, body, save_mock):
        resp = put(client, "/api/v2/selection", body)
        assert resp.status_code == 400
        assert error_code(resp) == "invalid_request"
        save_mock.assert_not_called()


# ----------------------------------------------------------------------
# First-run suggestion
# ----------------------------------------------------------------------


class TestSuggestion:
    def test_fits_remaining_quota(self, client, agent, backend):
        agent.quota_cache.store({"used": 190, "limit": 200})
        data = get(client, "/api/v2/first-run/suggestion?max=3").get_json()
        assert data["reason"] == "ok"
        # big (50 pages, most recent) does not fit 10 -> skipped
        assert [nb["uuid"] for nb in data["notebooks"]] == ["meeting", "diary"]
        assert data["notebooks"][0] == {"uuid": "meeting", "name": "Meeting Notes", "page_count": 3}
        assert data["total_pages"] == 8
        assert data["quota"] == {"limit": 200, "remaining": 10}
        assert backend.calls == []

    def test_unlimited(self, client, agent):
        agent.quota_cache.store({"used": 0, "limit": -1})
        data = get(client, "/api/v2/first-run/suggestion?max=2").get_json()
        assert [nb["uuid"] for nb in data["notebooks"]] == ["big", "meeting"]
        assert data["quota"] == {"limit": -1, "remaining": None}

    def test_fetches_quota_when_not_cached(self, client, backend):
        data = get(client, "/api/v2/first-run/suggestion").get_json()
        assert data["quota"] == {"limit": 200, "remaining": 196}
        assert any(call.endswith("/quota/status") for call in backend.calls)

    def test_quota_fetch_failure(self, client, backend):
        backend.status = 500
        resp = get(client, "/api/v2/first-run/suggestion")
        assert resp.status_code == 502
        assert error_code(resp) == "cloud_error"

    def test_quota_exhausted(self, client, agent):
        agent.quota_cache.store({"used": 200, "limit": 200})
        data = get(client, "/api/v2/first-run/suggestion").get_json()
        assert data["reason"] == "quota_exhausted" and data["notebooks"] == []

    def test_not_signed_in(self, client, cloud_sync):
        cloud_sync.authenticated = False
        data = get(client, "/api/v2/first-run/suggestion").get_json()
        assert data == {"notebooks": [], "total_pages": 0, "quota": None, "reason": "not_signed_in"}

    def test_folder_unavailable(self, client, config, agent, tmp_path):
        agent.quota_cache.store({"used": 0, "limit": 200})
        config.remarkable.source_directory = str(tmp_path / "nowhere")
        assert get(client, "/api/v2/first-run/suggestion").get_json()["reason"] == "folder_unavailable"

    @pytest.mark.parametrize("value", ["0", "x", "100", "-1"])
    def test_bad_max(self, client, value):
        resp = get(client, f"/api/v2/first-run/suggestion?max={value}")
        assert resp.status_code == 400 and error_code(resp) == "invalid_request"


# ----------------------------------------------------------------------
# Sync start / progress / resume
# ----------------------------------------------------------------------


class FakeInitialSync:
    instances: list["FakeInitialSync"] = []

    def __init__(self, config, cloud_sync, on_progress=None):
        self.release = threading.Event()
        self.selected = "unset"
        self.on_progress = on_progress
        self.result = {"notebooks": 1, "pages": 3, "failed": 0, "skipped": 0, "rate_limited": 0,
                       "stopped_reason": None}
        FakeInitialSync.instances.append(self)

    async def run(self, selected_uuids=None):
        self.selected = selected_uuids
        while not self.release.is_set():
            await asyncio.sleep(0.01)
        return self.result


@pytest.fixture
def fake_initial_sync():
    FakeInitialSync.instances = []
    with patch("app.sync.initial_sync.InitialSync", FakeInitialSync):
        yield FakeInitialSync


def _wait_progress(client, state, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        data = get(client, "/api/v2/sync/progress").get_json()
        if data["state"] == state:
            return data
        time.sleep(0.01)
    raise AssertionError(f"never reached {state}")


class TestSyncStart:
    def test_start_saves_selection_and_page_limit(self, client, config, save_mock, fake_initial_sync):
        config.sync.sync_all_notebooks = True
        resp = post(client, "/api/v2/sync/start", {"notebook_uuids": ["meeting", "diary"], "page_limit": 2})
        assert resp.status_code == 202 and resp.get_json() == {"ok": True}
        assert config.sync.sync_all_notebooks is False
        assert config.sync.selected_notebooks == ["meeting", "diary"]
        assert config.sync.max_pages_per_notebook == 2
        save_mock.assert_called()
        progress = _wait_progress(client, "running")
        # Pages this run will try: newest 2 of each notebook (limit 2)
        assert progress["counts"]["pages_total"] == 4
        (job,) = fake_initial_sync.instances
        deadline = time.monotonic() + 5
        while job.selected == "unset" and time.monotonic() < deadline:
            time.sleep(0.01)
        assert job.selected == ["meeting", "diary"]
        job.release.set()
        done = _wait_progress(client, "done")
        assert done["outcome"] == "success"
        assert done["counts"]["uploaded"] == 3
        assert done["finished_at"].endswith("Z")

    def test_page_limit_omitted_or_null_keeps_saved_limit(self, client, config, fake_initial_sync):
        config.sync.max_pages_per_notebook = 5
        config.sync.selected_notebooks = ["diary"]
        assert post(client, "/api/v2/sync/start", {"page_limit": None}).status_code == 202
        assert config.sync.max_pages_per_notebook == 5
        fake_initial_sync.instances[0].release.set()
        _wait_progress(client, "done")
        assert post(client, "/api/v2/sync/start").status_code == 202
        assert config.sync.max_pages_per_notebook == 5
        fake_initial_sync.instances[1].release.set()

    def test_without_body_syncs_current_selection(self, client, config, fake_initial_sync):
        config.sync.selected_notebooks = ["diary"]
        assert post(client, "/api/v2/sync/start").status_code == 202
        (job,) = fake_initial_sync.instances
        deadline = time.monotonic() + 5
        while job.selected == "unset" and time.monotonic() < deadline:
            time.sleep(0.01)
        assert job.selected == ["diary"]
        job.release.set()

    def test_already_running(self, client, fake_initial_sync):
        assert post(client, "/api/v2/sync/start").status_code == 202
        resp = post(client, "/api/v2/sync/start", {"notebook_uuids": ["big"]})
        assert resp.status_code == 409 and error_code(resp) == "sync_already_running"
        fake_initial_sync.instances[0].release.set()

    def test_not_signed_in(self, client, cloud_sync, fake_initial_sync, save_mock):
        cloud_sync.authenticated = False
        resp = post(client, "/api/v2/sync/start", {"notebook_uuids": ["big"]})
        assert resp.status_code == 401 and error_code(resp) == "not_signed_in"
        assert fake_initial_sync.instances == []
        save_mock.assert_not_called()

    @pytest.mark.parametrize(
        "body",
        [{"page_limit": 0}, {"page_limit": "3"}, {"page_limit": True}, {"notebook_uuids": []},
         {"notebook_uuids": "big"}],
    )
    def test_invalid(self, client, body, fake_initial_sync):
        resp = post(client, "/api/v2/sync/start", body)
        assert resp.status_code == 400 and error_code(resp) == "invalid_request"

    def test_core_not_ready(self, config, cloud_sync, fake_initial_sync):
        app = create_app(config, cloud_sync, agent=None, agent_loop=None, app_token=TOKEN)
        resp = post(app.test_client(), "/api/v2/sync/start")
        assert resp.status_code == 503 and error_code(resp) == "core_not_ready"
        assert get(app.test_client(), "/api/v2/sync/progress").get_json()["state"] == "idle"

    def test_progress_idle_shape(self, client):
        data = get(client, "/api/v2/sync/progress").get_json()
        assert data == {
            "state": "idle",
            "outcome": None,
            "counts": {"uploaded": 0, "failed": 0, "left_out_by_page_limit": 0, "will_retry": 0,
                       "notebooks_done": 0, "notebooks_total": 0, "pages_total": None},
            "started_at": None,
            "finished_at": None,
        }

    def test_resume(self, client, agent):
        queue = MagicMock()
        agent.file_watcher = SimpleNamespace(sync_queue=queue)
        assert post(client, "/api/v2/sync/resume").get_json() == {"ok": True}
        queue.request_resume.assert_called_once()

    def test_resume_without_watcher(self, client):
        assert post(client, "/api/v2/sync/resume").get_json() == {"ok": True}


class TestPagesTotal:
    def test_already_uploaded_pages_are_not_counted(self, client, config, library, fake_initial_sync):
        manifest = UploadManifest.for_config(config)
        for page in (library / "diary").glob("*.rm"):
            manifest.record_upload(page, fingerprint_file(page))
        assert post(client, "/api/v2/sync/start", {"notebook_uuids": ["diary", "meeting"]}).status_code == 202
        # diary's 5 pages are already uploaded: only meeting's 3 remain
        assert _wait_progress(client, "running")["counts"]["pages_total"] == 3
        fake_initial_sync.instances[0].release.set()

    def test_changed_page_counts_again(self, client, config, library, fake_initial_sync):
        manifest = UploadManifest.for_config(config)
        pages = sorted((library / "diary").glob("*.rm"))
        for page in pages:
            manifest.record_upload(page, fingerprint_file(page))
        pages[0].write_bytes(b"edited since the upload")
        assert post(client, "/api/v2/sync/start", {"notebook_uuids": ["diary"]}).status_code == 202
        assert _wait_progress(client, "running")["counts"]["pages_total"] == 1
        fake_initial_sync.instances[0].release.set()

    def test_other_host_uploads_do_not_count(self, client, config, library, fake_initial_sync):
        other = UploadManifest(UploadManifest.for_config(config).db_path, "rmirror.io")
        for page in (library / "diary").glob("*.rm"):
            other.record_upload(page, fingerprint_file(page))
        assert post(client, "/api/v2/sync/start", {"notebook_uuids": ["diary"]}).status_code == 202
        assert _wait_progress(client, "running")["counts"]["pages_total"] == 5
        fake_initial_sync.instances[0].release.set()


class TestProgressMapping:
    def _done(self, stats):
        job = InitialSyncJob()
        job.try_begin()
        job.finish(stats)
        return job

    @pytest.mark.parametrize(
        "stats, outcome",
        [
            ({"pages": 3, "failed": 0, "skipped": 1, "rate_limited": 2}, "success"),
            ({"pages": 3, "failed": 1, "skipped": 0, "rate_limited": 0}, "partial"),
            ({"pages": 0, "failed": 2, "skipped": 0, "rate_limited": 0}, "failed"),
            ({"pages": 1, "failed": 0, "skipped": 0, "rate_limited": 0, "stopped_reason": "quota"}, "stopped_quota"),
            ({"pages": 1, "failed": 4, "skipped": 0, "rate_limited": 0, "stopped_reason": "sign_in"},
             "stopped_sign_in"),
        ],
    )
    def test_outcomes(self, stats, outcome):
        from app.web.routes_v2 import sync_progress

        data = sync_progress(self._done(stats), pages_total=10)
        assert data["state"] == "done"
        assert data["outcome"] == outcome
        assert data["counts"]["left_out_by_page_limit"] == stats["skipped"]
        assert data["counts"]["will_retry"] == stats["rate_limited"]
        assert data["counts"]["pages_total"] == 10

    def test_error_is_failed(self):
        from app.web.routes_v2 import sync_progress

        job = InitialSyncJob()
        job.try_begin()
        job.fail("boom")
        data = sync_progress(job)
        assert (data["state"], data["outcome"]) == ("done", "failed")
        assert set(data["counts"]) == {"uploaded", "failed", "left_out_by_page_limit", "will_retry",
                                       "notebooks_done", "notebooks_total", "pages_total"}

    def test_running_with_live_counts(self):
        from app.web.routes_v2 import sync_progress

        job = InitialSyncJob()
        job.try_begin()
        job.update_progress({"notebooks_total": 3, "notebooks_done": 1, "uploaded": 4, "failed": 0,
                             "skipped": 0, "rate_limited": 0})
        data = sync_progress(job)
        assert data["state"] == "running" and data["outcome"] is None
        assert data["counts"]["notebooks_total"] == 3 and data["counts"]["uploaded"] == 4
        assert data["started_at"].endswith("Z") and data["finished_at"] is None


# ----------------------------------------------------------------------
# Settings, sign-out, deleted notebooks, update check
# ----------------------------------------------------------------------


class TestSettings:
    def test_get(self, client, config):
        config.sync.max_pages_per_notebook = 4
        data = get(client, "/api/v2/settings").get_json()
        assert data == {
            "page_limit": 4,
            "source_directory": config.remarkable.source_directory,
            "environment": {"name": "custom", "api_url": config.api.url},
            "environment_presets": {
                "production": "https://rmirror.io/api/v1",
                "staging": "https://staging.rmirror.io/api/v1",
            },
        }

    def test_page_limit_set_and_cleared(self, client, config, save_mock):
        assert put(client, "/api/v2/settings", {"page_limit": 7}).get_json() == {"ok": True, "needs_sign_in": False}
        assert config.sync.max_pages_per_notebook == 7
        put(client, "/api/v2/settings", {"page_limit": None})
        assert config.sync.max_pages_per_notebook is None
        assert save_mock.call_count == 2

    def test_source_directory_goes_through_the_agent(self, client, config, agent, tmp_path):
        new_dir = tmp_path / "other"
        new_dir.mkdir()
        assert put(client, "/api/v2/settings", {"source_directory": str(new_dir)}).status_code == 200
        assert agent.folder_changes == [str(new_dir.resolve())]
        assert config.remarkable.source_directory == str(new_dir.resolve())
        # Same folder again: nothing to do
        put(client, "/api/v2/settings", {"source_directory": str(new_dir)})
        assert agent.folder_changes == [str(new_dir.resolve())]

    @pytest.mark.parametrize(
        "api_url", ["http://rmirror.io/api/v1", "http://192.168.1.10:8000/api/v1", "ftp://x/api", "https:///x"]
    )
    def test_custom_environment_must_be_https_unless_loopback(self, client, config, api_url):
        resp = put(client, "/api/v2/settings", {"environment": {"name": "custom", "api_url": api_url}})
        assert resp.status_code == 400 and error_code(resp) == "invalid_request"
        assert config.api.url == "http://test-api.rmirror.io/api/v1"

    @pytest.mark.parametrize("api_url", ["http://localhost:8000/api/v1", "http://127.0.0.1:8000/v1", "https://my.example:8443/api/v1"])
    def test_custom_environment_allowed(self, client, config, mock_keychain, api_url):
        mock_keychain.get_token.side_effect = lambda host: None
        assert put(client, "/api/v2/settings", {"environment": {"name": "custom", "api_url": api_url}}).status_code == 200
        assert config.api.url == api_url

    def test_environment_change_refused_during_sync(self, client, config, fake_initial_sync):
        assert post(client, "/api/v2/sync/start").status_code == 202
        resp = put(client, "/api/v2/settings", {"environment": {"name": "staging"}})
        assert resp.status_code == 409 and error_code(resp) == "sync_already_running"
        assert config.api.url == "http://test-api.rmirror.io/api/v1"
        fake_initial_sync.instances[0].release.set()

    def test_switch_environment_without_stored_sign_in(self, client, config, cloud_sync, agent, mock_keychain):
        agent.quota_cache.store({"used": 1, "limit": 30})
        mock_keychain.get_token.side_effect = lambda host: None
        resp = put(client, "/api/v2/settings", {"environment": {"name": "staging"}})
        assert resp.get_json() == {"ok": True, "needs_sign_in": True}
        assert config.api.url == "https://staging.rmirror.io/api/v1"
        assert cloud_sync.authenticated is False
        assert agent.quota_cache.snapshot() is None
        assert agent.reauthenticated == 0

    def test_switch_environment_with_stored_sign_in(self, client, config, agent, mock_keychain):
        mock_keychain.get_token.side_effect = lambda host: "tok" if host == "my.example" else None
        resp = put(client, "/api/v2/settings", {"environment": {"name": "custom", "api_url": "https://my.example/api/v1"}})
        assert resp.get_json() == {"ok": True, "needs_sign_in": False}
        deadline = time.monotonic() + 5
        while agent.reauthenticated == 0 and time.monotonic() < deadline:
            time.sleep(0.01)
        assert agent.reauthenticated == 1

    @pytest.mark.parametrize(
        "body",
        [None, {"page_limit": 0}, {"source_directory": ""}, {"environment": "staging"},
         {"environment": {"name": "moon"}}, {"environment": {"name": "custom", "api_url": "ftp://x"}},
         {"page_limit": 3, "environment": {"name": "moon"}}],
    )
    def test_invalid(self, client, config, body, save_mock):
        resp = put(client, "/api/v2/settings", body)
        assert resp.status_code == 400 and error_code(resp) == "invalid_request"
        assert config.sync.max_pages_per_notebook is None
        save_mock.assert_not_called()


class TestSignOut:
    def test_sign_out_clears_and_stops_watcher(self, client, cloud_sync, agent, mock_keychain):
        agent.quota_cache.store({"used": 1, "limit": 30})
        resp = post(client, "/api/v2/auth/sign-out")
        assert resp.get_json() == {"ok": True}
        assert cloud_sync.authenticated is False
        assert agent.stopped_watcher is True
        assert agent.quota_cache.snapshot() is None
        mock_keychain.delete_token.assert_called_once()


class TestDeletedNotebooks:
    def test_list_shape(self, client):
        data = get(client, "/api/v2/deleted-notebooks").get_json()
        assert data == {
            "deleted_notebooks": [{"uuid": "gone-1", "name": "Old notes", "deleted_at": "2026-11-01T10:00:00Z"}]
        }

    def test_signed_out_is_empty(self, client, cloud_sync, backend):
        cloud_sync.authenticated = False
        assert get(client, "/api/v2/deleted-notebooks").get_json() == {"deleted_notebooks": []}
        assert backend.calls == []

    def test_resync(self, client, config, backend, save_mock):
        config.sync.excluded_notebooks = ["gone-1"]
        resp = post(client, "/api/v2/deleted-notebooks/gone-1", {"action": "resync"})
        assert resp.get_json() == {"ok": True}
        assert config.sync.excluded_notebooks == []
        assert "POST /api/v1/sync/deleted-notebooks/gone-1/acknowledge" in backend.calls

    def test_dismiss_keeps_exclusion(self, client, config):
        config.sync.excluded_notebooks = ["gone-1"]
        assert post(client, "/api/v2/deleted-notebooks/gone-1", {"action": "dismiss"}).status_code == 200
        assert config.sync.excluded_notebooks == ["gone-1"]

    def test_bad_action(self, client):
        resp = post(client, "/api/v2/deleted-notebooks/gone-1", {"action": "delete"})
        assert resp.status_code == 400 and error_code(resp) == "invalid_request"

    def test_not_signed_in(self, client, cloud_sync):
        cloud_sync.authenticated = False
        resp = post(client, "/api/v2/deleted-notebooks/gone-1", {"action": "dismiss"})
        assert resp.status_code == 401 and error_code(resp) == "not_signed_in"

    def test_cloud_error(self, client, backend):
        backend.status = 500
        resp = post(client, "/api/v2/deleted-notebooks/gone-1", {"action": "dismiss"})
        assert resp.status_code == 502 and error_code(resp) == "cloud_error"


class TestUpdateCheck:
    def test_shape(self, client):
        from app.updater import UpdateInfo

        info = UpdateInfo(has_update=True, current_version="2.0.0", latest_version="2.0.1",
                          download_url="https://example/x.dmg", release_notes="notes")
        with patch("app.updater.check_for_updates", new=AsyncMock(return_value=info)):
            data = get(client, "/api/v2/update-check").get_json()
        assert data == {"has_update": True, "current_version": "2.0.0", "latest_version": "2.0.1",
                        "download_url": "https://example/x.dmg"}

    def test_error(self, client):
        from app.updater import UpdateInfo

        info = UpdateInfo(has_update=False, current_version="2.0.0", latest_version="2.0.0", error="x")
        with patch("app.updater.check_for_updates", new=AsyncMock(return_value=info)):
            resp = get(client, "/api/v2/update-check")
        assert resp.status_code == 502 and error_code(resp) == "cloud_error"

    def test_timeout(self, client):
        async def slow():
            await asyncio.sleep(5)

        with patch("app.updater.check_for_updates", new=slow), patch("app.web.routes_v2.QUICK_TIMEOUT_SECONDS", 0.05):
            resp = get(client, "/api/v2/update-check")
        assert resp.status_code == 504 and error_code(resp) == "cloud_timeout"


# ----------------------------------------------------------------------
# Headless sign-in result pages
# ----------------------------------------------------------------------


FORBIDDEN_WORDS = ("token", "callback", "state")


def _bridge_url(client) -> str:
    """The sign-in URL the app gets from POST /api/v2/auth/begin (path and query)."""
    url = post(client, "/api/v2/auth/begin").get_json()["url"]
    return url[len(f"http://127.0.0.1:{PORT}"):]


class TestHeadlessSignIn:
    def _bridge_state(self, client):
        resp = MagicMock(status_code=200)
        resp.json.return_value = {"clerk_publishable_key": "pk_live_x"}
        with patch.object(routes.httpx, "get", return_value=resp):
            location = client.get(_bridge_url(client), base_url=BASE_URL).headers["Location"]
        from urllib.parse import parse_qs, urlparse

        callback = parse_qs(urlparse(location).query)["callback"][0]
        return parse_qs(urlparse(callback).query)["state"][0]

    def test_success_page_does_not_redirect(self, client, config, mock_keychain, save_mock):
        state = self._bridge_state(client)
        with patch.object(routes, "verify_agent_token", new=AsyncMock(return_value=True)), \
                patch.object(routes, "register_agent_with_backend", new=AsyncMock()):
            resp = client.get("/auth/callback", query_string={"state": state, "token": "new"}, base_url=BASE_URL)
        # Leaves the URL that carries the token at once
        assert resp.status_code == 303
        assert resp.headers["Location"] == "/auth/done"
        assert config.api.token == "new"
        save_mock.assert_called_once()
        done = client.get("/auth/done", base_url=BASE_URL)
        assert done.status_code == 200
        html = done.get_data(as_text=True)
        assert "You're signed in." in html
        assert "rmirror://signed-in" in html
        assert "new" not in html.split("<body>")[1]

    def test_done_page_takes_no_input(self, client):
        resp = client.get("/auth/done", query_string={"message": "<script>x</script>", "token": "t"}, base_url=BASE_URL)
        html = resp.get_data(as_text=True)
        assert "<script>x" not in html and "You're signed in." in html

    @pytest.mark.parametrize("case", ["no_state", "no_token", "rejected"])
    def test_failure_pages_use_plain_wording(self, client, config, case):
        params = {}
        if case != "no_state":
            params["state"] = self._bridge_state(client)
        if case == "rejected":
            params["token"] = "bad"
        with patch.object(routes, "verify_agent_token", new=AsyncMock(return_value=False)):
            resp = client.get("/auth/callback", query_string=params, base_url=BASE_URL)
        html = resp.get_data(as_text=True)
        body = html[html.index("<body>"):].lower()
        assert "sign-in did not work" in body
        for word in FORBIDDEN_WORDS:
            assert word not in body, word
        assert config.api.token == "test-jwt-token"

    def test_bridge_failure_is_plain(self, client):
        with patch.object(routes.httpx, "get", side_effect=httpx.ConnectError("down")):
            resp = client.get(_bridge_url(client), base_url=BASE_URL)
        assert resp.status_code == 502
        body = resp.get_data(as_text=True).lower()
        assert "clerk" not in body[body.index("<body>"):]


# ----------------------------------------------------------------------
# Review fixes at the route level
# ----------------------------------------------------------------------


class TestAuthState:
    @pytest.mark.parametrize("agent_state, expected", [
        ("checking", "checking"), ("offline", "offline"), ("signed_out", "signed_out"), ("signed_in", "signed_out"),
    ])
    def test_not_authenticated(self, client, cloud_sync, agent, agent_state, expected):
        cloud_sync.authenticated = False
        agent.auth_state = agent_state
        auth = get(client, "/api/v2/state").get_json()["auth"]
        assert auth["state"] == expected
        assert auth["signed_in"] is False

    def test_signed_in_wins(self, client, agent):
        agent.auth_state = "offline"
        assert get(client, "/api/v2/state").get_json()["auth"]["state"] == "signed_in"

    def test_sign_out_sets_signed_out(self, client, agent, mock_keychain):
        post(client, "/api/v2/auth/sign-out")
        assert agent.auth_state == "signed_out"
        assert get(client, "/api/v2/state").get_json()["auth"]["state"] == "signed_out"


class TestFirstSyncRule:
    def _app(self, config, cloud_sync, agent_loop):
        app = create_app(config, cloud_sync, agent=None, agent_loop=agent_loop, app_token=TOKEN, headless=True)
        return app.test_client()

    def test_fresh_install_is_not_completed(self, config, cloud_sync, agent_loop):
        config.sync.sync_all_notebooks = True  # the default
        config.sync.selected_notebooks = []
        client = self._app(config, cloud_sync, agent_loop)
        assert get(client, "/api/v2/state").get_json()["first_sync"]["completed"] is False

    def test_legacy_selection_counts_as_completed(self, config, cloud_sync, agent_loop):
        config.sync.sync_all_notebooks = False
        config.sync.selected_notebooks = ["diary"]
        client = self._app(config, cloud_sync, agent_loop)
        assert get(client, "/api/v2/state").get_json()["first_sync"]["completed"] is True

    def test_selection_saved_by_the_app_does_not_count(self, client, config, save_mock):
        put(client, "/api/v2/selection", {"sync_all": False, "selected_notebooks": ["diary"]})
        assert get(client, "/api/v2/state").get_json()["first_sync"]["completed"] is False


class TestSyncStartChecks:
    def test_unknown_notebooks_are_refused(self, client, config, save_mock, fake_initial_sync):
        resp = post(client, "/api/v2/sync/start", {"notebook_uuids": ["nope", "also-nope"]})
        assert resp.status_code == 400 and error_code(resp) == "invalid_request"
        save_mock.assert_not_called()
        assert fake_initial_sync.instances == []

    def test_selection_unchanged_when_already_running(self, client, config, fake_initial_sync):
        assert post(client, "/api/v2/sync/start", {"notebook_uuids": ["diary"]}).status_code == 202
        resp = post(client, "/api/v2/sync/start", {"notebook_uuids": ["big"], "page_limit": 9})
        assert resp.status_code == 409
        assert config.sync.selected_notebooks == ["diary"]
        assert config.sync.max_pages_per_notebook is None
        fake_initial_sync.instances[0].release.set()

    def test_concurrent_starts_run_one_job_with_its_selection(self, client, config, fake_initial_sync):
        results = []

        def start(uuid):
            results.append((uuid, post(client.application.test_client(), "/api/v2/sync/start",
                                       {"notebook_uuids": [uuid]}).status_code))

        threads = [threading.Thread(target=start, args=(u,)) for u in ("diary", "meeting", "big")]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        winners = [u for u, code in results if code == 202]
        assert len(winners) == 1 and sorted(code for _, code in results) == [202, 409, 409]
        assert config.sync.selected_notebooks == winners
        fake_initial_sync.instances[0].release.set()

    def test_job_released_when_loop_is_gone(self, config, cloud_sync, fake_initial_sync, save_mock):
        app = create_app(config, cloud_sync, agent=None, agent_loop=None, app_token=TOKEN, headless=True)
        c = app.test_client()
        assert post(c, "/api/v2/sync/start").status_code == 503
        assert app.config["INITIAL_SYNC_JOB"].snapshot()["state"] == "idle"


class TestSuggestionCounts:
    def test_orphan_pages_count(self, client, agent, library):
        agent.quota_cache.store({"used": 0, "limit": 8}, host="test-api.rmirror.io:80")
        # meeting: 3 pages in .content + 2 orphans = 5; diary 5 -> only one fits in 8
        for i in range(2):
            (library / "meeting" / f"orphan-{i}.rm").write_bytes(b"x")
        data = get(client, "/api/v2/first-run/suggestion").get_json()
        assert data["total_pages"] <= 8
        assert [nb["uuid"] for nb in data["notebooks"]] == ["meeting"]
        assert data["notebooks"][0]["page_count"] == 5

    def test_page_limit_caps_counts(self, client, config, agent):
        agent.quota_cache.store({"used": 0, "limit": 12}, host="test-api.rmirror.io:80")
        config.sync.max_pages_per_notebook = 4
        data = get(client, "/api/v2/first-run/suggestion").get_json()
        assert [nb["page_count"] for nb in data["notebooks"]] == [4, 3, 4]
        assert data["total_pages"] == 11

    def test_excluded_are_never_suggested(self, client, config, agent):
        agent.quota_cache.store({"used": 0, "limit": -1}, host="test-api.rmirror.io:80")
        config.sync.excluded_notebooks = ["big"]
        uuids = [nb["uuid"] for nb in get(client, "/api/v2/first-run/suggestion").get_json()["notebooks"]]
        assert "big" not in uuids

    def test_none_fit(self, client, agent):
        agent.quota_cache.store({"used": 198, "limit": 200}, host="test-api.rmirror.io:80")
        data = get(client, "/api/v2/first-run/suggestion").get_json()
        assert data["reason"] == "none_fit" and data["notebooks"] == []
        assert data["quota"] == {"limit": 200, "remaining": 2}

    def test_quota_of_previous_host_is_not_used(self, client, agent, backend):
        agent.quota_cache.store({"used": 0, "limit": 5}, host="rmirror.io")
        data = get(client, "/api/v2/first-run/suggestion").get_json()
        assert data["quota"] == {"limit": 200, "remaining": 196}
        assert any(call.endswith("/quota/status") for call in backend.calls)


class TestBridgeTicket:
    def _clerk(self):
        resp = MagicMock(status_code=200)
        resp.json.return_value = {"clerk_publishable_key": "pk_live_x"}
        return patch.object(routes.httpx, "get", return_value=resp)

    def test_begin_requires_app_token(self, client, app):
        resp = client.post("/api/v2/auth/begin", base_url=BASE_URL)
        assert resp.status_code == 401 and error_code(resp) == "bad_app_token"
        assert app.config["BRIDGE_TICKETS"]._tickets == {}

    def test_begin_returns_bridge_url(self, client):
        data = post(client, "/api/v2/auth/begin").get_json()
        assert set(data) == {"url"}
        assert data["url"].startswith(f"http://127.0.0.1:{PORT}/auth/bridge?ticket=")
        assert len(data["url"].split("ticket=")[1]) >= 43

    @pytest.mark.parametrize("case", ["missing", "wrong", "used", "expired"])
    def test_bridge_refuses_without_valid_ticket(self, client, app, case):
        query = {}
        if case == "wrong":
            post(client, "/api/v2/auth/begin")
            query = {"ticket": "x" * 43}
        elif case == "used":
            path = _bridge_url(client)
            with self._clerk():
                assert client.get(path, base_url=BASE_URL).status_code == 302
            query = {"ticket": path.split("ticket=")[1]}
        elif case == "expired":
            query = {"ticket": _bridge_url(client).split("ticket=")[1]}
        states_before = dict(app.config["AUTH_STATES"]._states)
        clock = (
            patch("app.web.shared.time.monotonic", return_value=time.monotonic() + 601)
            if case == "expired"
            else contextlib.nullcontext()
        )
        with self._clerk() as clerk, clock:
            resp = client.get("/auth/bridge", query_string=query, base_url=BASE_URL)
        assert resp.status_code == 403
        body = resp.get_data(as_text=True)
        assert "Open rMirror and select Sign in again." in body
        assert app.config["AUTH_STATES"]._states == states_before  # no state issued
        clerk.assert_not_called()  # the cloud was not asked

    def test_ticket_is_single_use_and_bridge_works(self, client, app):
        path = _bridge_url(client)
        with self._clerk():
            first = client.get(path, base_url=BASE_URL)
            second = client.get(path, base_url=BASE_URL)
        assert first.status_code == 302 and "callback=" in first.headers["Location"]
        assert "ticket" not in first.headers["Location"]
        assert len(app.config["AUTH_STATES"]._states) == 1
        assert second.status_code == 403

    def test_store_is_bounded(self, app):
        from app.web.shared import MAX_BRIDGE_TICKETS

        store = app.config["BRIDGE_TICKETS"]
        first = store.issue()
        for _ in range(MAX_BRIDGE_TICKETS):
            store.issue()
        assert len(store._tickets) == MAX_BRIDGE_TICKETS
        assert store.consume(first) is False

    def test_legacy_bridge_needs_no_ticket(self, config, cloud_sync, agent_loop):
        legacy = create_app(config, cloud_sync, agent=None, agent_loop=agent_loop).test_client()
        with self._clerk():
            resp = legacy.get("/auth/bridge", base_url=BASE_URL)
        assert resp.status_code == 302
        assert legacy.post("/api/v2/auth/begin", base_url=BASE_URL).status_code == 200

    def test_ticket_is_redacted_from_access_log(self):
        import logging

        from app.logging_config import RedactQuerySecretsFilter

        record = logging.LogRecord(
            "werkzeug", logging.INFO, __file__, 1,
            '127.0.0.1 - - [x] "GET /auth/bridge?ticket=SECRETTICKET HTTP/1.1" 302 -', None, None,
        )
        RedactQuerySecretsFilter().filter(record)
        assert "SECRETTICKET" not in record.getMessage()
        assert "ticket=[REDACTED]" in record.getMessage()

    def test_ticket_not_in_app_logs(self, client, caplog):
        import logging

        with caplog.at_level(logging.DEBUG):
            path = _bridge_url(client)
            with self._clerk():
                client.get(path, base_url=BASE_URL)
        assert path.split("ticket=")[1] not in caplog.text
