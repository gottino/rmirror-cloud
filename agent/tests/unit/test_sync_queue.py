"""
Tests for the sync queue: trailing debounce, manifest skips and error handling.
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.sync.cloud_sync import (
    AuthenticationRequiredError,
    CloudSyncError,
    QuotaExceededError,
    RateLimitError,
)
from app.sync.manifest import UploadManifest, fingerprint_file
from app.sync.queue import PAUSED_QUOTA, PAUSED_SIGN_IN, SyncQueue


class FakeTime:
    """Fake monotonic clock whose sleep just advances the clock."""

    def __init__(self):
        self.now = 1000.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


@pytest.fixture
def fake_time():
    return FakeTime()


@pytest.fixture
def manifest(tmp_path):
    return UploadManifest(tmp_path / "manifest.sqlite3", "api.example.test")


@pytest.fixture
def cloud_sync():
    cs = MagicMock()
    cs.authenticated = True
    cs.upload_file = AsyncMock(return_value={"success": True})
    return cs


@pytest.fixture
def statuses():
    return []


@pytest.fixture
def queue(test_config, cloud_sync, manifest, fake_time, statuses):
    test_config.sync.cooldown_seconds = 5
    test_config.sync.batch_size = 10
    q = SyncQueue(
        test_config,
        cloud_sync,
        manifest=manifest,
        on_status=statuses.append,
        clock=fake_time.clock,
        sleep=fake_time.sleep,
    )
    q.metadata_sync = MagicMock()
    q.metadata_sync.run = AsyncMock(return_value={"success": True})
    return q


def make_files(tmp_path: Path, count: int, notebook: str = "nb-1") -> list[Path]:
    d = tmp_path / "src" / notebook
    d.mkdir(parents=True, exist_ok=True)
    files = []
    for i in range(count):
        f = d / f"page-{i}.rm"
        f.write_bytes(f"content {i}".encode())
        files.append(f)
    return files


def uploaded_paths(cloud_sync) -> list[Path]:
    return [c.args[0] for c in cloud_sync.upload_file.await_args_list]


async def add_all(queue, files, notebook="nb-1"):
    for f in files:
        await queue.add(f, notebook, "rm")


class TestTrailingDebounce:
    async def test_item_waits_until_path_is_quiet(self, queue, tmp_path, fake_time):
        (f,) = make_files(tmp_path, 1)
        await queue.add(f, "nb-1", "rm")

        fake_time.now += 4
        assert queue._flush_due() == 0
        await queue.add(f, "nb-1", "rm")  # another write restarts the wait
        fake_time.now += 4
        assert queue._flush_due() == 0
        fake_time.now += 1
        assert queue._flush_due() == 1
        assert queue.queue.qsize() == 1

    async def test_burst_of_writes_uploads_final_content_once(self, queue, tmp_path, fake_time, cloud_sync, manifest):
        (f,) = make_files(tmp_path, 1)
        for version in (b"v1", b"v2", b"final"):
            f.write_bytes(version)
            await queue.add(f, "nb-1", "rm")
            fake_time.now += 1

        fake_time.now += 5
        stats = await queue._run_once()

        assert stats["uploaded"] == 1
        assert cloud_sync.upload_file.await_count == 1
        assert manifest.get(f).sha256 == fingerprint_file(f).sha256
        f.write_bytes(b"final")
        assert manifest.changed_fingerprint(f) is None

    async def test_paths_are_debounced_independently(self, queue, tmp_path, fake_time):
        a, b = make_files(tmp_path, 2)
        await queue.add(a, "nb-1", "rm")
        fake_time.now += 3
        await queue.add(b, "nb-1", "rm")
        fake_time.now += 2
        assert queue._flush_due() == 1  # only a has been quiet for 5s
        fake_time.now += 3
        assert queue._flush_due() == 1


class TestManifestSkip:
    async def test_unchanged_file_is_not_uploaded(self, queue, tmp_path, fake_time, cloud_sync, manifest):
        (f,) = make_files(tmp_path, 1)
        manifest.record_upload(f, fingerprint_file(f))

        await queue.add(f, "nb-1", "rm")
        fake_time.now += 5
        stats = await queue._run_once()

        assert stats["skipped"] == 1
        cloud_sync.upload_file.assert_not_awaited()

    async def test_unchanged_baseline_file_is_not_uploaded(self, queue, tmp_path, fake_time, cloud_sync, manifest):
        (f,) = make_files(tmp_path, 1)
        manifest.record_baseline(f, fingerprint_file(f))

        await queue.add(f, "nb-1", "rm")
        fake_time.now += 5
        await queue._run_once()
        cloud_sync.upload_file.assert_not_awaited()

    async def test_missing_file_is_dropped(self, queue, tmp_path, fake_time, cloud_sync):
        (f,) = make_files(tmp_path, 1)
        await queue.add(f, "nb-1", "rm")
        f.unlink()
        fake_time.now += 5
        stats = await queue._run_once()
        assert stats["failed"] == 1
        assert queue.queue.qsize() == 0
        cloud_sync.upload_file.assert_not_awaited()

    async def test_retry_later_skip_is_not_recorded(self, queue, tmp_path, fake_time, cloud_sync, manifest):
        content = tmp_path / "nb-1.content"
        content.write_text("{}")
        cloud_sync.upload_file.return_value = {"success": True, "skipped": True, "reason": "notebook_not_found"}

        await queue.add(content, "nb-1", "content")
        fake_time.now += 5
        await queue._run_once()

        assert manifest.get(content) is None

    async def test_deliberate_skip_is_recorded(self, queue, tmp_path, fake_time, cloud_sync, manifest):
        meta = tmp_path / "tpl.metadata"
        meta.write_text("{}")
        cloud_sync.upload_file.return_value = {"success": True, "skipped": True, "reason": "template"}

        await queue.add(meta, "tpl", "metadata")
        fake_time.now += 5
        await queue._run_once()

        assert manifest.get(meta) is not None


class TestErrorHandling:
    async def _queue_files(self, queue, files, fake_time):
        await add_all(queue, files)
        fake_time.now += 5

    async def test_rate_limit_mid_batch_loses_no_items(self, queue, tmp_path, fake_time, cloud_sync, manifest):
        files = make_files(tmp_path, 3)
        calls = {"n": 0}

        async def upload(path, uuid, ftype):
            calls["n"] += 1
            if calls["n"] == 2:
                raise RateLimitError("slow down", retry_after=30)
            return {"success": True}

        cloud_sync.upload_file.side_effect = upload
        await self._queue_files(queue, files, fake_time)

        stats = await queue._run_once()
        assert stats["uploaded"] == 1
        assert stats["requeued"] == 2
        assert fake_time.sleeps == [30]
        assert queue.queue.qsize() == 2

        stats = await queue._run_once()
        assert stats["uploaded"] == 2
        assert all(manifest.changed_fingerprint(f) is None for f in files)

    async def test_rate_limit_wait_is_capped(self, queue, tmp_path, fake_time, cloud_sync):
        files = make_files(tmp_path, 1)
        cloud_sync.upload_file.side_effect = RateLimitError("slow down", retry_after=10_000)
        await self._queue_files(queue, files, fake_time)

        await queue._run_once()
        assert fake_time.sleeps == [300]
        assert queue.queue.qsize() == 1

    async def test_quota_exceeded_pauses_and_keeps_items(self, queue, tmp_path, fake_time, cloud_sync, statuses):
        files = make_files(tmp_path, 3)
        cloud_sync.upload_file.side_effect = QuotaExceededError("quota")
        await self._queue_files(queue, files, fake_time)

        stats = await queue._run_once()
        assert stats["requeued"] == 3
        assert queue.paused_reason == PAUSED_QUOTA
        assert queue.get_stats()["paused_reason"] == PAUSED_QUOTA
        assert statuses[-1] == "Paused: quota exceeded"

        # Still paused before the re-check interval
        cloud_sync.upload_file.side_effect = None
        fake_time.now += 14 * 60
        assert await queue._run_once() is None
        assert cloud_sync.upload_file.await_count == 1

        # After 15 minutes it tries again
        fake_time.now += 60
        stats = await queue._run_once()
        assert stats["uploaded"] == 3
        assert queue.paused_reason is None
        assert statuses[-1] == "Watching"

    async def test_quota_pause_resumes_on_user_trigger(self, queue, tmp_path, fake_time, cloud_sync):
        files = make_files(tmp_path, 1)
        cloud_sync.upload_file.side_effect = QuotaExceededError("quota")
        await self._queue_files(queue, files, fake_time)
        await queue._run_once()
        assert queue.paused_reason == PAUSED_QUOTA

        cloud_sync.upload_file.side_effect = None
        queue.request_resume()
        stats = await queue._run_once()
        assert stats["uploaded"] == 1

    async def test_network_errors_retry_with_capped_backoff(self, queue, tmp_path, fake_time, cloud_sync, manifest):
        (f,) = make_files(tmp_path, 1)
        failures = [CloudSyncError("down", transient=True)] * 10
        cloud_sync.upload_file.side_effect = [*failures, {"success": True}]
        await self._queue_files(queue, [f], fake_time)

        stats = await queue._run_once()
        assert stats["uploaded"] == 1
        assert stats["retried"] == 10
        assert fake_time.sleeps == [2, 4, 8, 16, 32, 64, 128, 256, 300, 300]
        assert manifest.changed_fingerprint(f) is None

    async def test_server_error_is_retried(self, queue, tmp_path, fake_time, cloud_sync):
        (f,) = make_files(tmp_path, 1)
        cloud_sync.upload_file.side_effect = [
            CloudSyncError("bad gateway", status_code=502, transient=True),
            {"success": True},
        ]
        await self._queue_files(queue, [f], fake_time)
        stats = await queue._run_once()
        assert stats["uploaded"] == 1

    async def test_permanent_client_error_drops_item_only(self, queue, tmp_path, fake_time, cloud_sync, manifest):
        bad, good = make_files(tmp_path, 2)

        async def upload(path, uuid, ftype):
            if path == bad:
                raise CloudSyncError("bad request", status_code=400)
            return {"success": True}

        cloud_sync.upload_file.side_effect = upload
        await self._queue_files(queue, [bad, good], fake_time)

        stats = await queue._run_once()
        assert stats == {"uploaded": 1, "failed": 1, "retried": 0, "skipped": 0, "requeued": 0}
        assert queue.queue.qsize() == 0
        assert manifest.get(bad) is None
        assert manifest.get(good) is not None
        assert fake_time.sleeps == []

    async def test_sign_in_required_pauses_until_signed_in(
        self, queue, tmp_path, fake_time, cloud_sync, statuses, test_config
    ):
        files = make_files(tmp_path, 2)
        cloud_sync.upload_file.side_effect = AuthenticationRequiredError("expired", status_code=401)
        cloud_sync.authenticated = False
        reconnect = AsyncMock()
        queue.on_reconnect = reconnect
        await self._queue_files(queue, files, fake_time)

        stats = await queue._run_once()
        assert stats["requeued"] == 2
        assert queue.paused_reason == PAUSED_SIGN_IN
        assert statuses[-1] == "Sign in required"

        # Time alone does not resume it
        fake_time.now += 3600
        assert await queue._run_once() is None
        reconnect.assert_not_awaited()

        # The user signs in again
        cloud_sync.upload_file.side_effect = None
        cloud_sync.authenticated = True
        test_config.api._token = "fresh-token"
        stats = await queue._run_once()
        assert stats["uploaded"] == 2
        reconnect.assert_awaited_once()
        assert queue.paused_reason is None


class TestWorkerLoop:
    async def test_worker_polls_while_idle_and_stops(self, queue, fake_time):
        async def stop_after_sleep(seconds):
            fake_time.sleeps.append(seconds)
            queue.running = False

        queue._sleep = stop_after_sleep
        queue.running = True
        await queue._worker()
        assert fake_time.sleeps == [queue.IDLE_POLL_SECONDS]

    async def test_status_callback_errors_are_ignored(self, queue, tmp_path, fake_time, cloud_sync):
        queue.on_status = MagicMock(side_effect=RuntimeError("tray gone"))
        files = make_files(tmp_path, 1)
        cloud_sync.upload_file.side_effect = QuotaExceededError("quota")
        await add_all(queue, files)
        fake_time.now += 5
        await queue._run_once()
        assert queue.paused_reason == PAUSED_QUOTA
