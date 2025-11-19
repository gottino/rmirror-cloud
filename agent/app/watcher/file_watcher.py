"""
File watcher for monitoring reMarkable Desktop app folder.

Monitors the reMarkable sync folder for file changes and triggers cloud sync.
Based on the file watcher implementation from rm-int-src.
"""

import asyncio
from pathlib import Path
from typing import Optional

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from app.config import Config
from app.sync.cloud_sync import CloudSync
from app.sync.queue import SyncQueue


class ReMarkableEventHandler(FileSystemEventHandler):
    """Handler for reMarkable file system events."""

    # File extensions we care about
    RELEVANT_EXTENSIONS = {".content", ".metadata", ".pagedata", ".rm", ".pdf", ".epub"}

    def __init__(self, sync_queue: SyncQueue, loop: asyncio.AbstractEventLoop):
        """Initialize event handler."""
        super().__init__()
        self.sync_queue = sync_queue
        self.loop = loop

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

        # For moved events, use the destination path; otherwise use the source path
        file_path_str = getattr(event, 'dest_path', event.src_path)
        file_path = Path(file_path_str)

        # Check if we should ignore this file
        if self._should_ignore_file(file_path_str):
            return

        # Extract notebook UUID
        notebook_uuid = self._extract_notebook_uuid(file_path)
        if not notebook_uuid:
            return

        # Get file type
        file_type = self._get_file_type(file_path)

        print(f"📝 Detected change: {file_path.name} (UUID: {notebook_uuid}, type: {file_type})")

        # Add to sync queue from the watchdog thread
        # Use run_coroutine_threadsafe to schedule in the main event loop
        asyncio.run_coroutine_threadsafe(
            self.sync_queue.add(file_path, notebook_uuid, file_type),
            self.loop
        )


class FileWatcher:
    """
    File watcher for monitoring reMarkable Desktop app folder.

    Uses the watchdog library to monitor the folder for changes and
    automatically sync files to the cloud.
    """

    def __init__(self, config: Config, cloud_sync: CloudSync):
        """Initialize file watcher."""
        self.config = config
        self.cloud_sync = cloud_sync
        self.sync_queue = SyncQueue(config, cloud_sync)

        self.observer: Optional[Observer] = None
        self.running = False

    async def start(self) -> None:
        """Start watching the reMarkable folder."""
        source_dir = Path(self.config.remarkable.source_directory)

        if not source_dir.exists():
            raise FileNotFoundError(
                f"reMarkable folder not found: {source_dir}\n"
                "Please ensure the reMarkable Desktop app is installed and has synced at least once."
            )

        print(f"👁  Watching: {source_dir}")

        # Start sync queue
        await self.sync_queue.start()

        # Create and start observer
        self.observer = Observer()
        loop = asyncio.get_event_loop()
        event_handler = ReMarkableEventHandler(self.sync_queue, loop)
        self.observer.schedule(event_handler, str(source_dir), recursive=True)
        self.observer.start()

        self.running = True
        print("✓ File watcher started")
        print(f"  Observer is alive: {self.observer.is_alive()}")
        print(f"  Observer watching {len(self.observer.emitters)} emitter(s)")

        # Keep running
        try:
            while self.running:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass

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
