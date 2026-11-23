"""
Fixes from the security / correctness review of the headless core:
keychain namespacing, initial-sync deferral, folder switch baseline, page
counts, sign-in state, first-sync rule, quota host tag and quiet access log.
"""

import asyncio
import json
import logging
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agent_loop import AgentLoop
from app.config import APIConfig, keychain_account_for_url
from app.logging_config import DropPollingAccessLogFilter
from app.main import AUTH_CHECKING, AUTH_OFFLINE, AUTH_SIGNED_IN, AUTH_SIGNED_OUT, Agent
from app.remarkable.library import DocumentInfo
from app.sync.cloud_sync import AuthenticationRequiredError, CloudSyncError, RateLimitError
from app.sync.first_run import suggest_first_sync
from app.sync.initial_sync import InitialSync
from app.sync.manifest import UploadManifest, fingerprint_file
from app.sync.quota_cache import QuotaCache
from app.watcher.file_watcher import ReMarkableEventHandler, scan_for_changes

# ----------------------------------------------------------------------
# S2: keychain account per server
# ----------------------------------------------------------------------


class TestKeychainAccount:
    @pytest.mark.parametrize(
        "url, account",
        [
            # Existing keys keep resolving (production, staging, local development)
            ("https://rmirror.io/api/v1", "rmirror.io"),
            ("https://staging.rmirror.io/api/v1", "staging.rmirror.io"),
            ("https://rmirror.io:443/api/v1", "rmirror.io"),
            ("http://localhost:8000/v1", "localhost"),
            ("http://127.0.0.1:8000/api/v1", "127.0.0.1"),
            ("http://[::1]:8000/api/v1", "::1"),
            # Never the production key for another port or plain http
            ("https://rmirror.io:8443/api/v1", "rmirror.io:8443"),
            ("http://rmirror.io/api/v1", "rmirror.io:80"),
            ("http://rmirror.io:8080/api/v1", "rmirror.io:8080"),
        ],
    )
    def test_derivation(self, url, account):
        assert keychain_account_for_url(url) == account

    def test_existing_production_token_still_resolves(self, mock_keychain):
        mock_keychain.get_token.side_effect = lambda account: "stored" if account == "rmirror.io" else None
        assert APIConfig(url="https://rmirror.io/api/v1").token == "stored"
        assert APIConfig(url="http://rmirror.io/api/v1").token is None
        assert APIConfig(url="https://rmirror.io:8443/api/v1").token is None


# ----------------------------------------------------------------------
# S3: rate limit / sign-in stop leave pages for the rescan
# ----------------------------------------------------------------------

NB = "test-notebook-uuid-1234"


def _add_pages(folder: Path, count: int) -> list[str]:
    ids = [f"extra-{i}" for i in range(count)]
    content = json.loads((folder / f"{NB}.content").read_text())
    content["pages"] = content["pages"] + ids
    (folder / f"{NB}.content").write_text(json.dumps(content))
    for page_id in ids:
        (folder / NB / f"{page_id}.rm").write_bytes(page_id.encode())
    return ids


@pytest.fixture
def setup(test_config, temp_remarkable_dir, tmp_path):
    test_config.remarkable.source_directory = str(temp_remarkable_dir)
    test_config.sync.sync_all_notebooks = True
    manifest = UploadManifest(tmp_path / "m.sqlite3", "host")
    handler = ReMarkableEventHandler(MagicMock(), test_config)
    # First run of the watcher: everything present is baseline
    assert scan_for_changes(temp_remarkable_dir, handler, manifest) == []
    sync = InitialSync(test_config, AsyncMock(), manifest=manifest)
    sync.metadata_sync.run = AsyncMock(return_value={"success": True})
    sync._sleep = AsyncMock()
    return sync, manifest, handler, temp_remarkable_dir


def _rescanned(folder, handler, manifest) -> set[str]:
    """Page files the next rescan would upload (the test edits .content/.metadata itself)."""
    return {
        path.name
        for path, _uuid, file_type in scan_for_changes(folder, handler, manifest)
        if file_type == "rm"
    }


class TestInitialSyncDeferral:
    async def test_rate_limit_leaves_page_and_rest_for_rescan(self, setup, test_config):
        sync, manifest, handler, folder = setup
        _add_pages(folder, 3)  # 5 pages now; .content order oldest -> newest
        manifest_files = sorted((folder / NB).glob("*.rm"))
        for f in manifest_files:
            manifest.record_baseline(f, fingerprint_file(f))
        test_config.sync.max_pages_per_notebook = 3
        calls = {"n": 0}

        async def upload(path, uuid, ftype):
            calls["n"] += 1
            if calls["n"] == 1:
                return {"success": True}
            raise RateLimitError("slow down", retry_after=1)

        sync.cloud_sync.upload_file.side_effect = upload
        stats = await sync.run()

        assert stats["pages"] == 1
        assert stats["skipped"] == 2  # page limit
        assert stats["rate_limited"] == 2  # the limited page and the one after it
        assert stats["pages"] + stats["failed"] + stats["skipped"] + stats["rate_limited"] == 5
        assert sync.progress["rate_limited"] == 2

        uploaded = [p for p in manifest_files if (manifest.get(p) and not manifest.get(p).is_baseline)]
        assert len(uploaded) == 1
        # Deferred pages: not marked uploaded, picked up by the next rescan
        again = _rescanned(folder, handler, manifest)
        assert again == {"extra-1.rm", "extra-0.rm"}
        assert all(manifest.get(folder / NB / name) is None for name in again)
        # Pages left out by the page limit stay baseline
        assert all(name.endswith(".rm") for name in again)

    async def test_sign_in_stop_defers_this_and_later_notebooks(self, setup):
        sync, manifest, handler, folder = setup
        # A second notebook after the first
        other = "zz-second"
        (folder / f"{other}.metadata").write_text(json.dumps({"visibleName": "Second", "type": "DocumentType", "lastOpened": "1"}))
        (folder / f"{other}.content").write_text(json.dumps({"pages": ["s1"]}))
        (folder / other).mkdir()
        (folder / other / "s1.rm").write_bytes(b"s1")
        manifest.record_baseline(folder / other / "s1.rm", fingerprint_file(folder / other / "s1.rm"))

        sync.cloud_sync.upload_file.side_effect = AuthenticationRequiredError("signed out", status_code=401)
        stats = await sync.run()

        assert stats["stopped_reason"] == "sign_in"
        assert stats["failed"] == 0
        assert stats["rate_limited"] == 3  # 2 pages here + 1 in the notebook not reached
        assert sync.cloud_sync.upload_file.await_count == 1
        assert len(_rescanned(folder, handler, manifest)) == 3

    async def test_excluded_notebooks_are_skipped(self, setup, test_config):
        sync, manifest, handler, folder = setup
        test_config.sync.excluded_notebooks = [NB]
        sync.cloud_sync.upload_file.return_value = {"success": True}
        stats = await sync.run()
        assert stats["pages"] == 0
        sync.cloud_sync.upload_file.assert_not_awaited()


# ----------------------------------------------------------------------
# S4: switching folders records the new folder as baseline
# ----------------------------------------------------------------------


class TestFolderSwitch:
    def test_new_folder_is_baselined_not_uploaded(self, test_config, temp_remarkable_dir, tmp_path):
        old = tmp_path / "old"
        old.mkdir()
        test_config.remarkable.source_directory = str(old)
        test_config.remarkable.watch_enabled = True
        test_config.sync.sync_all_notebooks = True

        manifest = UploadManifest.for_config(test_config)
        manifest.mark_initialised()  # the watcher already ran for this server

        loop = AgentLoop()
        loop.start()
        agent = Agent(test_config, agent_loop=loop, headless=True)
        agent.running = True
        cloud_sync = MagicMock(authenticated=True)
        cloud_sync.upload_file = AsyncMock(return_value={"success": True})
        agent.cloud_sync = cloud_sync
        try:
            with patch.object(type(test_config), "save"):
                state = loop.run(agent.change_source_directory(str(temp_remarkable_dir)), timeout=10)
            assert state == "ok"
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline and not (agent.file_watcher and agent.file_watcher.running):
                time.sleep(0.05)
            assert agent.file_watcher and agent.file_watcher.running
            stats = agent.file_watcher.sync_queue.get_stats()
            assert stats["pending"] == 0 and stats["queue_size"] == 0
            pages = list((temp_remarkable_dir / NB).glob("*.rm"))
            assert pages and all(manifest.get(p).is_baseline for p in pages)
            cloud_sync.upload_file.assert_not_called()
            assert agent._baseline_pending is None
        finally:
            loop.run(agent.stop_file_watcher(), timeout=10)
            loop.stop()


# ----------------------------------------------------------------------
# S5: suggestion reason none_fit
# ----------------------------------------------------------------------


def test_none_fit():
    docs = [DocumentInfo(uuid="big", name="Big", page_count=50)]
    s = suggest_first_sync(signed_in=True, folder_ok=True, documents=docs, remaining=10, max_count=3)
    assert (s.reason, s.notebooks) == ("none_fit", [])


# ----------------------------------------------------------------------
# S6: sign-in state with offline retry
# ----------------------------------------------------------------------


def _agent_with_cloud(test_config, outcomes):
    agent = Agent(test_config, headless=True, agent_loop=AgentLoop())
    agent.running = True
    cloud_sync = MagicMock(authenticated=False, user_email="a@b")
    results = list(outcomes)

    async def authenticate():
        outcome = results.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        cloud_sync.authenticated = True
        return True

    cloud_sync.authenticate = AsyncMock(side_effect=authenticate)
    cloud_sync.get_quota_status = AsyncMock(return_value={"used": 0, "limit": 30})
    agent.cloud_sync = cloud_sync
    agent._auth_retry_sleep = AsyncMock()
    return agent, cloud_sync


class TestSignInState:
    async def test_no_stored_sign_in(self, test_config, mock_keychain):
        agent, cloud_sync = _agent_with_cloud(test_config, [])
        await agent._initial_sign_in_check()
        assert agent.auth_state == AUTH_SIGNED_OUT
        cloud_sync.authenticate.assert_not_awaited()

    async def test_signed_in(self, test_config_with_token):
        agent, _ = _agent_with_cloud(test_config_with_token, [True])
        await agent._initial_sign_in_check()
        assert agent.auth_state == AUTH_SIGNED_IN

    async def test_rejected(self, test_config_with_token):
        agent, _ = _agent_with_cloud(test_config_with_token, [AuthenticationRequiredError("no", status_code=401)])
        await agent._initial_sign_in_check()
        assert agent.auth_state == AUTH_SIGNED_OUT

    async def test_offline_then_retried_with_backoff(self, test_config_with_token, caplog):
        offline = CloudSyncError("down", transient=True)
        agent, cloud_sync = _agent_with_cloud(test_config_with_token, [offline, offline, offline, True])
        with caplog.at_level(logging.INFO, logger="app.main"):
            await agent._initial_sign_in_check()
            assert agent.auth_state == AUTH_OFFLINE
            await asyncio.wait_for(agent._auth_retry_task, 5)
        assert agent.auth_state == AUTH_SIGNED_IN
        delays = [c.args[0] for c in agent._auth_retry_sleep.await_args_list]
        assert delays == [5.0, 10.0, 20.0]
        # One warning while offline, one line when back, no spam
        assert caplog.text.count("Could not reach rMirror Cloud") == 1

    async def test_backoff_is_capped(self, test_config_with_token):
        offline = CloudSyncError("down", transient=True)
        agent, _ = _agent_with_cloud(test_config_with_token, [offline] * 8 + [True])
        await agent._initial_sign_in_check()
        await asyncio.wait_for(agent._auth_retry_task, 5)
        delays = [c.args[0] for c in agent._auth_retry_sleep.await_args_list]
        assert max(delays) == 60.0 and delays[-1] == 60.0

    async def test_checking_state_while_check_runs(self, test_config_with_token):
        agent, cloud_sync = _agent_with_cloud(test_config_with_token, [])
        gate = asyncio.Event()

        async def slow():
            await gate.wait()
            cloud_sync.authenticated = True

        cloud_sync.authenticate = AsyncMock(side_effect=slow)
        task = asyncio.create_task(agent._initial_sign_in_check())
        await asyncio.sleep(0.05)
        assert agent.auth_state == AUTH_CHECKING
        gate.set()
        await task
        assert agent.auth_state == AUTH_SIGNED_IN


# ----------------------------------------------------------------------
# Quota cache host tag, quiet access log
# ----------------------------------------------------------------------


def test_quota_of_another_host_is_not_shown():
    cache = QuotaCache()
    cache.store({"used": 1, "limit": 30}, host="rmirror.io")
    assert cache.snapshot("rmirror.io")["limit"] == 30
    assert cache.snapshot("staging.rmirror.io") is None


@pytest.mark.parametrize(
    "line, kept",
    [
        ('127.0.0.1 - - [x] "GET /api/v2/state HTTP/1.1" 200 -', False),
        ('127.0.0.1 - - [x] "GET /health HTTP/1.1" 200 -', False),
        ('127.0.0.1 - - [x] "POST /api/v2/sync/start HTTP/1.1" 202 -', True),
        ('127.0.0.1 - - [x] "GET /api/v2/notebooks HTTP/1.1" 200 -', True),
    ],
)
def test_polling_access_lines_are_dropped(line, kept):
    record = logging.LogRecord("werkzeug", logging.INFO, __file__, 1, line, None, None)
    assert DropPollingAccessLogFilter().filter(record) is kept


async def test_sign_out_during_sync_ends_it_as_stopped_sign_in(test_config_with_token, temp_remarkable_dir, tmp_path):
    """The real CloudSync: after logout() the next page needs a sign-in, so the sync stops."""
    import httpx

    from app.sync.cloud_sync import CloudSync
    from app.web.routes_v2 import sync_progress
    from app.web.shared import InitialSyncJob

    config = test_config_with_token
    config.remarkable.source_directory = str(temp_remarkable_dir)
    cloud_sync = CloudSync(config)
    cloud_sync.authenticated = True

    def handler(request):
        if request.url.path.endswith("/processing/rm-file"):
            config.api._token = None
            with patch("app.config.get_keychain_manager") as keychain:
                keychain.return_value.get_token.return_value = None
                cloud_sync.logout()
        return httpx.Response(200, json={"success": True})

    cloud_sync.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    sync = InitialSync(config, cloud_sync, manifest=UploadManifest(tmp_path / "m.sqlite3", "h"))
    sync.metadata_sync.run = AsyncMock(return_value={"success": True})
    with patch("app.config.get_keychain_manager") as keychain:
        keychain.return_value.get_token.return_value = None
        stats = await sync.run()
    job = InitialSyncJob()
    job.try_begin()
    job.finish(stats)
    progress = sync_progress(job, pages_total=2)
    assert progress["outcome"] == "stopped_sign_in"
    assert progress["counts"]["uploaded"] == 1 and progress["counts"]["will_retry"] == 1
    await cloud_sync.close()
