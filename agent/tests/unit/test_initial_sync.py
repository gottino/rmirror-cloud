"""InitialSync: live progress counts and retries of server errors."""

from unittest.mock import AsyncMock

import pytest

from app.sync.cloud_sync import CloudSyncError
from app.sync.initial_sync import InitialSync
from app.sync.manifest import UploadManifest, fingerprint_file

NB = "test-notebook-uuid-1234"


@pytest.fixture
def manifest(tmp_path):
    return UploadManifest(tmp_path / "manifest.sqlite3", "test-host")


@pytest.fixture
def initial_sync(test_config, temp_remarkable_dir, manifest):
    test_config.remarkable.source_directory = str(temp_remarkable_dir)
    cloud_sync = AsyncMock()
    progress = []
    sync = InitialSync(test_config, cloud_sync, manifest=manifest, on_progress=progress.append)
    sync.metadata_sync.run = AsyncMock(return_value={"success": True})
    sync._sleep = AsyncMock()
    sync.progress_reports = progress
    return sync


def _pages(temp_remarkable_dir):
    return sorted((temp_remarkable_dir / NB).glob("*.rm"))


class TestProgress:
    async def test_counts_are_reported_while_running(self, initial_sync):
        initial_sync.cloud_sync.upload_file.return_value = {"success": True}

        stats = await initial_sync.run()

        assert stats["pages"] == 2
        reports = initial_sync.progress_reports
        assert reports[0]["notebooks_total"] == 1
        assert [r["uploaded"] for r in reports if r["uploaded"]][:2] == [1, 2]
        assert reports[-1] == {
            "notebooks_total": 1, "notebooks_done": 1, "uploaded": 2,
            "failed": 0, "skipped": 0, "rate_limited": 0,
        }

    async def test_failed_pages_are_counted(self, initial_sync):
        initial_sync.cloud_sync.upload_file.side_effect = CloudSyncError("bad request", status_code=400)

        stats = await initial_sync.run()

        assert stats["pages"] == 0
        assert stats["failed"] == 2
        assert initial_sync.progress_reports[-1]["failed"] == 2


class TestServerErrors:
    async def test_5xx_is_retried_with_backoff(self, initial_sync, temp_remarkable_dir):
        error = CloudSyncError("Internal Server Error", status_code=500, transient=True)
        initial_sync.cloud_sync.upload_file.side_effect = [error, error, {"success": True}, {"success": True}]

        stats = await initial_sync.run()

        assert stats["pages"] == 2
        assert stats["failed"] == 0
        delays = [call.args[0] for call in initial_sync._sleep.await_args_list]
        assert delays == [2, 4]

    async def test_4xx_is_not_retried(self, initial_sync):
        initial_sync.cloud_sync.upload_file.side_effect = CloudSyncError("bad", status_code=400)

        await initial_sync.run()

        assert initial_sync.cloud_sync.upload_file.await_count == 2  # once per page
        initial_sync._sleep.assert_not_awaited()

    async def test_page_still_failing_is_left_for_the_start_up_scan(
        self, initial_sync, manifest, temp_remarkable_dir
    ):
        pages = _pages(temp_remarkable_dir)
        # The start-up scan recorded both pages as baseline before the initial sync ran
        for page in pages:
            manifest.record_baseline(page, fingerprint_file(page))
        initial_sync.cloud_sync.upload_file.side_effect = CloudSyncError(
            "Internal Server Error", status_code=500, transient=True
        )

        stats = await initial_sync.run()

        assert stats["failed"] == 2
        attempts = initial_sync.cloud_sync.upload_file.await_count
        assert attempts == 2 * (InitialSync.SERVER_ERROR_RETRIES + 1)
        for page in pages:
            # Not marked as uploaded, and no longer a baseline: the next scan uploads it
            assert manifest.get(page) is None
            assert manifest.changed_fingerprint(page) is not None

    async def test_uploaded_page_is_recorded(self, initial_sync, manifest, temp_remarkable_dir):
        initial_sync.cloud_sync.upload_file.return_value = {"success": True}

        await initial_sync.run()

        for page in _pages(temp_remarkable_dir):
            assert manifest.get(page).uploaded_at is not None
