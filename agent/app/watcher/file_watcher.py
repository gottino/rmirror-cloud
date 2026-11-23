"""
File watcher for monitoring reMarkable Desktop app folder.

Monitors the reMarkable sync folder for file changes and triggers cloud sync.
Based on the file watcher implementation from rm-int-src.
"""

import asyncio
import logging
import os
import time
from collections.abc import Awaitable, Callable
from datetime import datetime
from pathlib import Path
from typing import Optional

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from app.config import Config
from app.remarkable.library import FOLDER_UNREADABLE, folder_state
from app.sync.cloud_sync import CloudSync
from app.sync.manifest import UploadManifest, fingerprint_file
from app.sync.queue import SyncQueue

logger = logging.getLogger(__name__)


class ReMarkableEventHandler(FileSystemEventHandler):
    """Handler for reMarkable file system events."""

    # File extensions we care about
    RELEVANT_EXTENSIONS = {".content", ".metadata", ".pagedata", ".rm", ".pdf", ".epub"}

    def __init__(self, sync_queue: SyncQueue, config: Config):
        """Initialize event handler."""
        super().__init__()
        self.sync_queue = sync_queue
        self.config = config
        # Wall-clock time of the last event watchdog delivered (any type), for /api/status
        self.last_event_at: datetime | None = None

    def _should_ignore_file(self, file_path: str) -> bool:
        """
        Check if a file should be ignored.

        Args:
            file_path: Path to the file

        Returns:
            True if file should be ignored, False otherwise
        """
        path = Path(file_path)

        # Ignore directories
        if path.is_dir():
            return True

        # Ignore hidden files and temp files
        if path.name.startswith(".") or path.name.endswith(".tmp"):
            return True

        # Only process reMarkable-specific files
        if path.suffix and path.suffix not in self.RELEVANT_EXTENSIONS:
            return True

        return False

    def _should_sync_notebook(self, notebook_uuid: str) -> bool:
        """
        Check if a notebook should be synced based on user selection and exclusions.

        Args:
            notebook_uuid: UUID of the notebook

        Returns:
            True if notebook should be synced, False otherwise
        """
        # Always skip excluded notebooks (e.g., deleted on server)
        if notebook_uuid in self.config.sync.excluded_notebooks:
            return False

        # If sync_all_notebooks is True, sync everything
        if self.config.sync.sync_all_notebooks:
            return True

        # Otherwise, only sync selected notebooks
        return notebook_uuid in self.config.sync.selected_notebooks

    def _extract_notebook_uuid(self, file_path: Path) -> Optional[str]:
        """
        Extract notebook UUID from file path.

        reMarkable files are named with the UUID of the notebook they belong to.
        For example: abc123.content, abc123.metadata, abc123/0.rm

        Args:
            file_path: Path to the file

        Returns:
            Notebook UUID or None if unable to extract
        """
        # For .rm files, the UUID is the parent directory name
        if file_path.suffix == ".rm":
            return file_path.parent.name

        # For other files, the UUID is the filename without extension
        return file_path.stem

    def _get_file_type(self, file_path: Path) -> str:
        """
        Get the file type for the sync queue.

        Args:
            file_path: Path to the file

        Returns:
            File type string (rm, metadata, content, pagedata, pdf, epub)
        """
        ext = file_path.suffix.lstrip(".")
        return ext

    def dispatch(self, event: FileSystemEvent) -> None:
        """
        Dispatch one event, never letting an error escape to watchdog.

        watchdog calls this on its observer thread. An exception raised here ends
        that thread (BaseObserver.run does not catch it), after which no further
        events are delivered while everything else looks healthy. So log the error
        for this one event and carry on with the next.
        """
        self.last_event_at = datetime.now()
        try:
            super().dispatch(event)
        except Exception as e:
            name = _event_file_name(event)
            logger.error(
                f"Error handling file event for {name} ({getattr(event, 'event_type', '?')}): {e}",
                exc_info=True,
            )

    def on_any_event(self, event: FileSystemEvent) -> None:
        """
        Handle any file system event.

        Args:
            event: File system event from watchdog
        """
        # Only process file events (not directory events)
        if event.is_directory:
            return

        # Only process creation, modification, and move events
        # The reMarkable Desktop app uses atomic writes (write to .cache, then move to final location)
        if event.event_type not in ("created", "modified", "moved"):
            return

        # For moved events, use the destination path; otherwise use the source path.
        # (watchdog 4+ sets dest_path to '' on non-move events, so check the type.)
        if event.event_type == "moved":
            file_path_str = event.dest_path or event.src_path
        else:
            file_path_str = event.src_path
        file_path = Path(file_path_str)

        # Check if we should ignore this file
        if self._should_ignore_file(file_path_str):
            return

        # Extract notebook UUID
        notebook_uuid = self._extract_notebook_uuid(file_path)
        if not notebook_uuid:
            return

        # Check if this notebook should be synced
        if not self._should_sync_notebook(notebook_uuid):
            print(f"⏭️  Skipping (not selected): {file_path.name} (UUID: {notebook_uuid})")
            return

        # Get file type
        file_type = self._get_file_type(file_path)

        logger.info(f"Detected change: {file_path.name} ({file_type})")
        print(f"📝 Detected change: {file_path.name} (UUID: {notebook_uuid}, type: {file_type})")

        # Hand the change to the sync queue. This runs on the watchdog thread;
        # note_change() only touches a lock-guarded dict, so no event loop is
        # needed here (the queue worker on the agent loop picks it up).
        self.sync_queue.note_change(file_path, notebook_uuid, file_type)


def _event_file_name(event: object) -> str:
    """The file name an event is about (for logs; never raises)."""
    try:
        path = getattr(event, "dest_path", "") or getattr(event, "src_path", "")
        if isinstance(path, bytes):
            path = os.fsdecode(path)
        return Path(path).name or str(path)
    except Exception:
        return "<unknown>"


def scan_for_changes(
    source_dir: Path,
    handler: ReMarkableEventHandler,
    manifest: UploadManifest,
    report_changes: bool = True,
) -> list[tuple[Path, str, str]]:
    """
    Walk the source folder and return the files that changed since the agent last saw them.

    Uses the watcher's own filters (``_should_ignore_file``, ``_extract_notebook_uuid``,
    ``_should_sync_notebook``), so the scan considers exactly the files the watcher would.

    Baseline rule: the first time this runs for an API host the manifest is empty.
    Uploading everything then would spend the user's OCR quota on the whole library
    without asking (first uploads go through the explicit initial sync, which has a
    page limit). So on that first run every existing file is recorded as a *baseline*
    (hash stored, not uploaded) and nothing is returned. From then on, files that are
    new or whose hash differs from their entry (baseline or uploaded) are returned.
    Files of notebooks that are not selected for sync are baselined if they have no
    entry yet, so selecting a notebook later does not upload its whole history either.

    Blocking (stats and hashes files); run it off the event loop.

    ``report_changes=False`` leaves logging the changed files to the caller (the
    periodic rescan logs its own line).

    Returns:
        (file_path, notebook_uuid, file_type) for each file to upload.
    """
    initialised = manifest.is_initialised()
    changed: list[tuple[Path, str, str]] = []
    baselined = 0

    for root, _dirs, files in os.walk(source_dir):
        for name in files:
            file_path = Path(root) / name
            if handler._should_ignore_file(str(file_path)):
                continue
            notebook_uuid = handler._extract_notebook_uuid(file_path)
            if not notebook_uuid:
                continue

            try:
                if not initialised or not handler._should_sync_notebook(notebook_uuid):
                    if manifest.get(file_path) is None:
                        if manifest.record_baseline(file_path, fingerprint_file(file_path)):
                            baselined += 1
                    continue

                if manifest.changed_fingerprint(file_path) is not None:
                    changed.append((file_path, notebook_uuid, handler._get_file_type(file_path)))
            except OSError as e:
                logger.debug(f"Skipping unreadable file during scan: {file_path}: {e}")

    if not initialised:
        manifest.mark_initialised()
        logger.info(f"Upload manifest initialised: {baselined} existing file(s) recorded as baseline")
        print(f"✓ Recorded {baselined} existing file(s) as already present (not uploaded)")
    elif changed and report_changes:
        logger.info(f"Start-up scan found {len(changed)} changed file(s)")
        print(f"🔎 Found {len(changed)} file(s) changed while the agent was not watching")

    return changed


def baseline_folder(source_dir: Path, handler: ReMarkableEventHandler, manifest: UploadManifest) -> int:
    """Record every existing file under source_dir as baseline (not uploaded) unless it has an entry.

    Used when the user points the agent at another folder: like the first run for
    an API host, the files already there must not be uploaded wholesale (that is
    what the initial sync with its page limit is for). Blocking; run off the loop.
    Returns the number of new baseline entries.
    """
    baselined = 0
    for root, _dirs, files in os.walk(source_dir):
        for name in files:
            file_path = Path(root) / name
            if handler._should_ignore_file(str(file_path)):
                continue
            if not handler._extract_notebook_uuid(file_path):
                continue
            try:
                if manifest.get(file_path) is None and manifest.record_baseline(
                    file_path, fingerprint_file(file_path)
                ):
                    baselined += 1
            except OSError as e:
                logger.debug(f"Skipping unreadable file during baseline: {file_path}: {e}")
    logger.info(f"Recorded {baselined} existing file(s) of {source_dir} as baseline")
    return baselined


class FileWatcher:
    """
    File watcher for monitoring reMarkable Desktop app folder.

    Uses the watchdog library to monitor the folder for changes and
    automatically sync files to the cloud. While running it also checks that the
    watchdog observer is still alive (restarting it and rescanning if not) and
    rescans the folder every ``sync.sync_interval`` seconds as a safety net for
    events that never arrive.
    """

    # How often the keep-running loop checks the observer
    HEALTH_CHECK_SECONDS = 1.0
    # Lower bound for sync.sync_interval, so a 0 or tiny value cannot spin
    MIN_RESCAN_INTERVAL_SECONDS = 30

    def __init__(
        self,
        config: Config,
        cloud_sync: CloudSync,
        on_status: Callable[[str], None] | None = None,
        manifest: UploadManifest | None = None,
        observer_factory: Callable[[], Observer] = Observer,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ):
        """Initialize file watcher.

        ``observer_factory``, ``clock`` and ``sleep`` are injectable for tests.
        """
        self.config = config
        self.cloud_sync = cloud_sync
        self.sync_queue = SyncQueue(config, cloud_sync, manifest=manifest, on_status=on_status)
        # Rescan when the queue resumes after the user signs in again
        self.sync_queue.on_reconnect = self.rescan

        self._observer_factory = observer_factory
        self._clock = clock
        self._sleep = sleep

        self.observer: Optional[Observer] = None
        self.event_handler: Optional[ReMarkableEventHandler] = None
        self.running = False

        # Health / visibility (reported in /api/status)
        self.observer_restarts = 0
        self._observer_failure_logged = False
        self._rescan_lock = asyncio.Lock()
        self.last_rescan_at: datetime | None = None
        self.last_rescan_reason: str | None = None
        self.last_rescan_result: str | None = None

    async def start(self) -> None:
        """Start watching the reMarkable folder; returns when the watcher is stopped."""
        source_dir = Path(self.config.remarkable.source_directory)

        if not source_dir.exists():
            raise FileNotFoundError(
                f"reMarkable folder not found: {source_dir}\n"
                "Please ensure the reMarkable Desktop app is installed and has synced at least once."
            )
        if folder_state(source_dir) == FOLDER_UNREADABLE:
            # A scan would see an empty folder (and baseline nothing); wait for access
            raise PermissionError(f"reMarkable folder cannot be read: {source_dir}")

        print(f"👁  Watching: {source_dir}")

        await self.sync_queue.start()

        self.event_handler = ReMarkableEventHandler(self.sync_queue, self.config)

        # First run for this backend: record the baseline before watching, so the
        # baseline cannot swallow a change made while it is being recorded.
        baseline_first = not await asyncio.to_thread(self.sync_queue.manifest.is_initialised)
        if baseline_first:
            await self._rescan_logged("start-up")

        self._start_observer()
        print(f"Observer started, is_alive: {self.observer.is_alive()}")

        # Later runs: scan after the observer is up, so no change slips between the two
        if not baseline_first:
            await self._rescan_logged("start-up")

        self.running = True
        print("✓ File watcher started")

        try:
            await self._keep_running()
        except asyncio.CancelledError:
            pass

    def _start_observer(self) -> None:
        """Create, schedule and start a watchdog observer for the source folder."""
        watch_dir = str(self.config.remarkable.source_directory)
        observer = self._observer_factory()
        observer.schedule(self.event_handler, watch_dir, recursive=True)
        observer.start()
        self.observer = observer
        logger.info(f"Observer watching {watch_dir}")

    def _rescan_interval(self) -> float:
        return float(max(self.config.sync.sync_interval, self.MIN_RESCAN_INTERVAL_SECONDS))

    async def _keep_running(self) -> None:
        """Until stopped: check the observer every second, rescan every sync_interval."""
        next_rescan = self._clock() + self._rescan_interval()
        while self.running:
            await self._sleep(self.HEALTH_CHECK_SECONDS)
            if not self.running:
                break
            await self._check_observer()
            if self.running and self._clock() >= next_rescan:
                await self._periodic_rescan()
                next_rescan = self._clock() + self._rescan_interval()

    def observer_alive(self) -> bool:
        """Whether the observer thread and all its emitter threads are running."""
        observer = self.observer
        if observer is None or not observer.is_alive():
            return False
        try:
            emitters = list(observer.emitters)
        except RuntimeError:  # set changed while copying; check again next time
            return True
        return all(emitter.is_alive() for emitter in emitters)

    async def _check_observer(self) -> None:
        """Replace a dead observer and rescan, so changes made meanwhile are not lost."""
        if not self.running or self.observer_alive():
            return

        if not self._observer_failure_logged:
            logger.error(
                "File watcher observer stopped unexpectedly; starting a new one and rescanning"
            )
            print("⚠️  File watcher stopped receiving events; restarting it")
            self._observer_failure_logged = True

        old = self.observer
        if old is not None:
            # stop() also stops and joins any emitter still running (without a
            # timeout), so do it off the loop and do not wait for it indefinitely
            try:
                await asyncio.wait_for(asyncio.to_thread(old.stop), timeout=5)
            except Exception as e:
                logger.debug(f"Stopping dead observer failed: {e!r}")
            if not self.running:
                return

        try:
            self._start_observer()
        except Exception as e:
            # Retried on the next check; logged once until it works again
            logger.debug(f"Restarting observer failed: {e}", exc_info=True)
            self.observer = None
            return

        self.observer_restarts += 1
        self._observer_failure_logged = False
        logger.info("Observer restarted")
        await self._rescan_logged("observer restart")

    async def _periodic_rescan(self) -> None:
        """Safety-net rescan; skipped if another rescan is still running."""
        if not self.running or self._rescan_lock.locked():
            return
        try:
            count = await self.rescan(reason="periodic")
        except Exception as e:
            logger.warning(f"Periodic rescan failed: {e}", exc_info=True)
            return
        if count:
            logger.info(f"Periodic rescan found {count} changed file(s)")
            print(f"🔎 Periodic rescan found {count} changed file(s)")

    async def rescan(self, reason: str = "reconnect") -> int:
        """Queue files that changed since they were last seen (see scan_for_changes).

        Rescans never overlap; a second caller waits for the first.
        """
        async with self._rescan_lock:
            source_dir = Path(self.config.remarkable.source_directory)
            handler = self.event_handler or ReMarkableEventHandler(self.sync_queue, self.config)
            try:
                changed = await asyncio.to_thread(
                    scan_for_changes,
                    source_dir,
                    handler,
                    self.sync_queue.manifest,
                    reason != "periodic",
                )
            except Exception as e:
                self._record_rescan(reason, f"failed: {e}")
                raise
            if reason == "periodic" and not self.running:
                # Stopped while scanning: leave the changes to the next start-up scan
                self._record_rescan(reason, "stopped")
                return 0
            for file_path, notebook_uuid, file_type in changed:
                await self.sync_queue.add(file_path, notebook_uuid, file_type)
            self._record_rescan(reason, f"{len(changed)} changed")
            return len(changed)

    def _record_rescan(self, reason: str, result: str) -> None:
        self.last_rescan_at = datetime.now()
        self.last_rescan_reason = reason
        self.last_rescan_result = result

    async def _rescan_logged(self, reason: str) -> None:
        """Rescan, but never let a scan failure stop the watcher."""
        try:
            await self.rescan(reason=reason)
        except Exception as e:
            logger.error(f"Rescan ({reason}) failed (watching continues): {e}", exc_info=True)

    async def stop(self) -> None:
        """Stop watching the reMarkable folder."""
        if not self.running:
            return

        print("Stopping file watcher...")
        # Clearing this first also ends the keep-running loop, so a deliberate stop
        # is never mistaken for a dead observer (no restart, no further rescans)
        self.running = False

        # Stop observer
        if self.observer:
            self.observer.stop()
            self.observer.join(timeout=5)

        # Stop sync queue
        await self.sync_queue.stop()

        print("File watcher stopped")

    def get_health(self) -> dict:
        """Observer and rescan state, for /api/status."""

        def iso(value: datetime | None) -> str | None:
            return value.isoformat(timespec="seconds") if value else None

        handler = self.event_handler
        return {
            "observer_alive": self.observer_alive(),
            "observer_restarts": self.observer_restarts,
            "last_event_at": iso(handler.last_event_at if handler else None),
            "last_rescan_at": iso(self.last_rescan_at),
            "last_rescan_reason": self.last_rescan_reason,
            "last_rescan_result": self.last_rescan_result,
        }

    def get_stats(self) -> dict:
        """Get watcher statistics."""
        queue_stats = self.sync_queue.get_stats()
        return {
            "running": self.running,
            "watching": str(self.config.remarkable.source_directory),
            "queue": queue_stats,
        }
