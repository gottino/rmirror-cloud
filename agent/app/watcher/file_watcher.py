"""
File watcher for monitoring reMarkable Desktop app folder.

Monitors the reMarkable sync folder for file changes and triggers cloud sync.
Based on the file watcher implementation from rm-int-src.
"""

import asyncio
import logging
import os
from collections.abc import Callable
from pathlib import Path
from typing import Optional

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from app.config import Config
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

        print(f"📝 Detected change: {file_path.name} (UUID: {notebook_uuid}, type: {file_type})")

        # Add to sync queue using the same pattern as rm-int-src
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._handle_file_change(file_path, notebook_uuid, file_type))
        except RuntimeError:
            # No event loop running - create a new one for this operation
            asyncio.run(self._handle_file_change(file_path, notebook_uuid, file_type))

    async def _handle_file_change(self, file_path: Path, notebook_uuid: str, file_type: str):
        """Handle file change asynchronously."""
        await self.sync_queue.add(file_path, notebook_uuid, file_type)


def scan_for_changes(
    source_dir: Path, handler: ReMarkableEventHandler, manifest: UploadManifest
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
    elif changed:
        logger.info(f"Start-up scan found {len(changed)} changed file(s)")
        print(f"🔎 Found {len(changed)} file(s) changed while the agent was not watching")

    return changed


class FileWatcher:
    """
    File watcher for monitoring reMarkable Desktop app folder.

    Uses the watchdog library to monitor the folder for changes and
    automatically sync files to the cloud.
    """

    def __init__(
        self,
        config: Config,
        cloud_sync: CloudSync,
        on_status: Callable[[str], None] | None = None,
        manifest: UploadManifest | None = None,
    ):
        """Initialize file watcher."""
        self.config = config
        self.cloud_sync = cloud_sync
        self.sync_queue = SyncQueue(config, cloud_sync, manifest=manifest, on_status=on_status)
        # Rescan when the queue resumes after the user signs in again
        self.sync_queue.on_reconnect = self.rescan

        self.observer: Optional[Observer] = None
        self.event_handler: Optional[ReMarkableEventHandler] = None
        self.running = False

    async def start(self) -> None:
        """Start watching the reMarkable folder - EXACT COPY OF ISOLATION TEST PATTERN."""
        source_dir = Path(self.config.remarkable.source_directory)

        if not source_dir.exists():
            raise FileNotFoundError(
                f"reMarkable folder not found: {source_dir}\n"
                "Please ensure the reMarkable Desktop app is installed and has synced at least once."
            )

        print(f"👁  Watching: {source_dir}")

        # EXACT PATTERN FROM ISOLATION TEST
        await self.sync_queue.start()

        self.event_handler = ReMarkableEventHandler(self.sync_queue, self.config)

        # First run for this backend: record the baseline before watching, so the
        # baseline cannot swallow a change made while it is being recorded.
        baseline_first = not await asyncio.to_thread(self.sync_queue.manifest.is_initialised)
        if baseline_first:
            await self._rescan_logged()

        self.observer = Observer()
        watch_dir = str(source_dir)
        print(f'Scheduling observer for: {watch_dir}')
        self.observer.schedule(self.event_handler, watch_dir, recursive=True)
        self.observer.start()
        print(f'Observer started, is_alive: {self.observer.is_alive()}')

        # Later runs: scan after the observer is up, so no change slips between the two
        if not baseline_first:
            await self._rescan_logged()

        self.running = True
        print("✓ File watcher started")

        # Keep running
        try:
            while self.running:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass

    async def rescan(self) -> int:
        """Queue files that changed while the agent was not watching (see scan_for_changes)."""
        source_dir = Path(self.config.remarkable.source_directory)
        handler = self.event_handler or ReMarkableEventHandler(self.sync_queue, self.config)
        changed = await asyncio.to_thread(scan_for_changes, source_dir, handler, self.sync_queue.manifest)
        for file_path, notebook_uuid, file_type in changed:
            await self.sync_queue.add(file_path, notebook_uuid, file_type)
        return len(changed)

    async def _rescan_logged(self) -> None:
        """Rescan, but never let a scan failure stop the watcher from starting."""
        try:
            await self.rescan()
        except Exception as e:
            logger.error(f"Start-up scan failed (watching continues): {e}", exc_info=True)

    async def stop(self) -> None:
        """Stop watching the reMarkable folder."""
        if not self.running:
            return

        print("Stopping file watcher...")
        self.running = False

        # Stop observer
        if self.observer:
            self.observer.stop()
            self.observer.join(timeout=5)

        # Stop sync queue
        await self.sync_queue.stop()

        print("File watcher stopped")

    def get_stats(self) -> dict:
        """Get watcher statistics."""
        queue_stats = self.sync_queue.get_stats()
        return {
            "running": self.running,
            "watching": str(self.config.remarkable.source_directory),
            "queue": queue_stats,
        }
