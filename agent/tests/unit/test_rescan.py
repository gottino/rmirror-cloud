"""
Tests for the start-up rescan (scan_for_changes), the first-run baseline rule,
and recording initial-sync uploads in the manifest.
"""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.config import ReMarkableConfig
from app.sync.initial_sync import InitialSync
from app.sync.manifest import UploadManifest
from app.sync.queue import SyncQueue
from app.watcher.file_watcher import FileWatcher, ReMarkableEventHandler, scan_for_changes

NB = "nb-aaaa"
OTHER = "nb-bbbb"


@pytest.fixture
def source(tmp_path) -> Path:
    src = tmp_path / "remarkable"
    for uuid in (NB, OTHER):
        (src / uuid).mkdir(parents=True)
        (src / uuid / "p1.rm").write_bytes(b"page one " + uuid.encode())
        (src / f"{uuid}.metadata").write_text('{"visibleName": "x"}')
        (src / f"{uuid}.content").write_text('{"pages": ["p1"]}')
    (src / f"{NB}.thumbnails").mkdir()
    (src / f"{NB}.thumbnails" / "p1.png").write_bytes(b"png")
    (src / ".hidden.rm").write_bytes(b"hidden")
    return src


@pytest.fixture
def manifest(tmp_path):
    return UploadManifest(tmp_path / "manifest.sqlite3", "api.example.test")


@pytest.fixture
def config(test_config, source):
    test_config.remarkable = ReMarkableConfig(source_directory=str(source), watch_enabled=True)
    return test_config


@pytest.fixture
def handler(config):
    return ReMarkableEventHandler(MagicMock(), config)


def names(changed):
    return sorted(p.relative_to(p.parents[1]).as_posix() if p.suffix == ".rm" else p.name for p, _, _ in changed)


class TestBaseline:
    def test_first_run_records_baseline_and_uploads_nothing(self, source, handler, manifest):
        assert scan_for_changes(source, handler, manifest) == []
        assert manifest.is_initialised()

        entry = manifest.get(source / NB / "p1.rm")
        assert entry is not None and entry.is_baseline
        # Filters applied: hidden files and other extensions are not recorded
        assert manifest.get(source / ".hidden.rm") is None
        assert manifest.get(source / f"{NB}.thumbnails" / "p1.png") is None

    def test_second_run_without_changes_finds_nothing(self, source, handler, manifest):
        scan_for_changes(source, handler, manifest)
        assert scan_for_changes(source, handler, manifest) == []


class TestRescan:
    def test_changed_and_new_files_are_returned(self, source, handler, manifest):
        scan_for_changes(source, handler, manifest)

        (source / NB / "p1.rm").write_bytes(b"edited while stopped")
        (source / NB / "p2.rm").write_bytes(b"new page")
        (source / f"{NB}.thumbnails" / "p2.png").write_bytes(b"ignored")

        changed = scan_for_changes(source, handler, manifest)
        assert names(changed) == [f"{NB}/p1.rm", f"{NB}/p2.rm"]
        assert {(uuid, ftype) for _, uuid, ftype in changed} == {(NB, "rm")}

    def test_metadata_files_use_watcher_uuid_and_type(self, source, handler, manifest):
        scan_for_changes(source, handler, manifest)
        (source / f"{NB}.metadata").write_text('{"visibleName": "renamed"}')

        changed = scan_for_changes(source, handler, manifest)
        assert [(p.name, uuid, ftype) for p, uuid, ftype in changed] == [(f"{NB}.metadata", NB, "metadata")]

    def test_excluded_notebook_is_not_returned(self, source, handler, manifest, config):
        scan_for_changes(source, handler, manifest)
        config.sync.excluded_notebooks = [OTHER]
        (source / OTHER / "p1.rm").write_bytes(b"changed")
        assert scan_for_changes(source, handler, manifest) == []

    def test_unselected_notebook_is_baselined_not_returned(self, source, handler, manifest, config):
        scan_for_changes(source, handler, manifest)
        config.sync.sync_all_notebooks = False
        config.sync.selected_notebooks = [NB]

        (source / OTHER / "p9.rm").write_bytes(b"new page in unselected notebook")
        (source / NB / "p9.rm").write_bytes(b"new page in selected notebook")

        changed = scan_for_changes(source, handler, manifest)
        assert names(changed) == [f"{NB}/p9.rm"]
        assert manifest.get(source / OTHER / "p9.rm").is_baseline

        # Selecting the notebook later does not upload its existing pages
        config.sync.selected_notebooks = [NB, OTHER]
        assert names(scan_for_changes(source, handler, manifest)) == [f"{NB}/p9.rm"]


class TestRestart:
    async def test_file_changed_while_stopped_uploads_after_restart(self, source, config, manifest):
        # First run: baseline only
        first = FileWatcher(config, MagicMock(), manifest=manifest)
        assert await first.rescan() == 0

        # Agent stopped; the user edits a page
        page = source / NB / "p1.rm"
        page.write_bytes(b"edited while the agent was stopped")

        # Restart: the rescan queues the page and the queue uploads it
        cloud_sync = MagicMock()
        cloud_sync.upload_file = AsyncMock(return_value={"success": True})
        now = [0.0]

        async def fake_sleep(seconds):
            now[0] += seconds

        watcher = FileWatcher(config, cloud_sync, manifest=manifest)
        watcher.sync_queue = SyncQueue(
            config, cloud_sync, manifest=manifest, clock=lambda: now[0], sleep=fake_sleep
        )
        watcher.sync_queue.metadata_sync = MagicMock(run=AsyncMock())
        assert await watcher.rescan() == 1

        now[0] += config.sync.cooldown_seconds
        stats = await watcher.sync_queue._run_once()
        assert stats["uploaded"] == 1
        cloud_sync.upload_file.assert_awaited_once_with(page, NB, "rm")
        assert manifest.changed_fingerprint(page) is None

    def test_file_watcher_wires_reconnect_rescan(self, config, manifest):
        watcher = FileWatcher(config, MagicMock(), manifest=manifest)
        assert watcher.sync_queue.on_reconnect == watcher.rescan


class TestInitialSyncRecordsUploads:
    async def test_uploaded_pages_are_recorded(self, source, config, manifest):
        cloud_sync = MagicMock()
        cloud_sync.upload_file = AsyncMock(return_value={"success": True})
        initial = InitialSync(config, cloud_sync, manifest=manifest)

        stats = await initial._sync_notebook_content(NB)

        assert stats["uploaded"] == 1
        entry = manifest.get(source / NB / "p1.rm")
        assert entry is not None and not entry.is_baseline
        assert manifest.get(source / OTHER / "p1.rm") is None

    async def test_rate_limited_page_is_not_recorded(self, source, config, manifest):
        cloud_sync = MagicMock()
        initial = InitialSync(config, cloud_sync, manifest=manifest)
        initial._upload_with_retry = AsyncMock(return_value={"rate_limited": True})

        await initial._sync_notebook_content(NB)
        assert manifest.get(source / NB / "p1.rm") is None


class TestWatcherEvents:
    """Real watchdog event objects reach the queue with the right path."""

    @pytest.fixture
    def recorder(self, config):
        added = []

        class Recorder:
            async def add(self, file_path, notebook_uuid, file_type):
                added.append((file_path, notebook_uuid, file_type))
                return True

        return ReMarkableEventHandler(Recorder(), config), added

    def test_created_modified_and_moved_events_are_queued(self, recorder, source):
        from watchdog.events import FileCreatedEvent, FileModifiedEvent, FileMovedEvent

        handler, added = recorder
        page = source / NB / "p1.rm"
        handler.on_any_event(FileCreatedEvent(str(page)))
        handler.on_any_event(FileModifiedEvent(str(page)))
        handler.on_any_event(FileMovedEvent(str(source / "tmp-write"), str(page)))

        assert added == [(page, NB, "rm")] * 3

    def test_moved_event_without_dest_falls_back_to_src(self, recorder, source):
        from watchdog.events import FileMovedEvent

        handler, added = recorder
        page = source / NB / "p1.rm"
        handler.on_any_event(FileMovedEvent(str(page), ""))
        assert added == [(page, NB, "rm")]

    def test_directory_events_are_ignored(self, recorder, source):
        from watchdog.events import DirCreatedEvent, DirModifiedEvent, DirMovedEvent

        handler, added = recorder
        handler.on_any_event(DirCreatedEvent(str(source / NB)))
        handler.on_any_event(DirModifiedEvent(str(source / NB)))
        handler.on_any_event(DirMovedEvent(str(source / "x"), str(source / NB)))
        assert added == []

    async def test_one_desktop_save_uploads_each_file_once(self, source, config, manifest):
        """created + modified + moved for the same path, debounced, gives a single upload."""
        from watchdog.events import FileCreatedEvent, FileModifiedEvent, FileMovedEvent

        scan_for_changes(source, ReMarkableEventHandler(MagicMock(), config), manifest)  # baseline

        cloud_sync = MagicMock()
        cloud_sync.upload_file = AsyncMock(return_value={"success": True})
        now = [0.0]

        async def fake_sleep(seconds):
            now[0] += seconds

        sync_queue = SyncQueue(config, cloud_sync, manifest=manifest, clock=lambda: now[0], sleep=fake_sleep)
        sync_queue.metadata_sync = MagicMock(run=AsyncMock())
        handler = ReMarkableEventHandler(sync_queue, config)

        page = source / NB / "p1.rm"
        meta = source / f"{NB}.metadata"
        page.write_bytes(b"saved by the desktop app")
        meta.write_text('{"visibleName": "saved"}')
        for path in (page, meta):
            handler.on_any_event(FileCreatedEvent(str(path)))
            handler.on_any_event(FileModifiedEvent(str(path)))
            handler.on_any_event(FileMovedEvent(str(source / "tmp"), str(path)))
            now[0] += 0.1

        # Called from inside a running loop, the handler schedules add() as tasks
        await asyncio.sleep(0)
        now[0] += config.sync.cooldown_seconds
        stats = await sync_queue._run_once()
        assert stats["uploaded"] == 2
        assert sorted(c.args[0].name for c in cloud_sync.upload_file.await_args_list) == sorted([page.name, meta.name])
        assert await sync_queue._run_once() is None
