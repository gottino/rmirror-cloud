"""
Sync queue for batching and deduplicating file uploads.

Uses two-phase sync architecture:
1. Sync metadata for notebook (fast, creates structure)
2. Upload page content (slow, with OCR)
"""

import asyncio
import logging
import threading
import time
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.config import Config
from app.sync.cloud_sync import (
    AuthenticationRequiredError,
    CloudSync,
    CloudSyncError,
    QuotaExceededError,
    RateLimitError,
)
from app.sync.manifest import UploadManifest
from app.sync.metadata_sync import MetadataSync

logger = logging.getLogger(__name__)

# Why the queue is paused (None when it is running normally)
PAUSED_QUOTA = "quota_exceeded"
PAUSED_SIGN_IN = "sign_in_required"

# Tray texts for each pause reason (shown via tray_app.update_status)
PAUSE_STATUS_TEXT = {
    PAUSED_QUOTA: "Paused: quota exceeded",
    PAUSED_SIGN_IN: "Sign in required",
}

# Upload results that the backend deliberately skipped but which must be retried
# later rather than recorded as done (the notebook does not exist yet).
_RETRY_LATER_SKIP_REASONS = {"notebook_not_found"}


@dataclass
class SyncItem:
    """Item in the sync queue."""

    file_path: Path
    notebook_uuid: str
    file_type: str
    added_at: datetime

    def __hash__(self) -> int:
        """Hash for deduplication."""
        return hash((str(self.file_path), self.notebook_uuid))

    def __eq__(self, other: object) -> bool:
        """Equality for deduplication."""
        if not isinstance(other, SyncItem):
            return False
        return self.file_path == other.file_path and self.notebook_uuid == other.notebook_uuid


def _should_record(result: object) -> bool:
    """Whether an upload_file() result means this file version is done."""
    if isinstance(result, dict) and result.get("skipped"):
        return result.get("reason") not in _RETRY_LATER_SKIP_REASONS
    return True


class SyncQueue:
    """
    Queue for managing file uploads to the cloud.

    Features:
    - Per-path trailing debounce: a path is queued once it has been quiet for
      ``sync.cooldown_seconds``, so a burst of writes uploads the final content
    - Skips files whose content matches the upload manifest
    - Batch processing for efficiency
    - Rate limits (429) put the rest of the batch back and wait for Retry-After
    - Quota exceeded (402) and sign-in required (401 after a failed re-auth)
      pause the queue and keep its items
    - Network errors and 5xx responses are retried with capped exponential backoff
    - Other 4xx responses are logged and the item is dropped

    The queue itself lives in memory; durability comes from the upload manifest
    plus the start-up rescan in ``FileWatcher``.
    """

    MAX_BACKOFF_SECONDS = 300
    MAX_RATE_LIMIT_WAIT_SECONDS = 300
    QUOTA_RECHECK_SECONDS = 15 * 60
    PAUSED_POLL_SECONDS = 5.0
    IDLE_POLL_SECONDS = 0.5

    def __init__(
        self,
        config: Config,
        cloud_sync: CloudSync,
        manifest: UploadManifest | None = None,
        on_status: Callable[[str], None] | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ):
        """
        Initialize sync queue.

        Args:
            config: Agent configuration
            cloud_sync: Cloud sync client
            manifest: Upload manifest (defaults to the one in the config directory)
            on_status: Optional callback for user-visible status text (the tray)
            clock: Monotonic clock, injectable for tests
            sleep: Async sleep, injectable for tests
        """
        self.config = config
        self.cloud_sync = cloud_sync
        self.metadata_sync = MetadataSync(config, cloud_sync)
        self.manifest = manifest if manifest is not None else UploadManifest.for_config(config)
        self.on_status = on_status
        self._clock = clock
        self._sleep = sleep

        self.queue: asyncio.Queue[SyncItem] = asyncio.Queue()
        # Debounce: path -> (latest item, time of the latest event). Written from
        # the watchdog thread, read by the worker, so guarded by a lock.
        self._pending: dict[str, tuple[SyncItem, float]] = {}
        self._pending_lock = threading.Lock()

        self.paused_reason: str | None = None
        self._paused_at: float = 0.0
        self._resume_requested = threading.Event()
        # Called when the queue resumes after sign-in (the "reconnect" rescan)
        self.on_reconnect: Callable[[], Awaitable[object]] | None = None

        self.running = False
        self.worker_task: Optional[asyncio.Task] = None

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def _set_status(self, text: str) -> None:
        if self.on_status is None:
            return
        try:
            self.on_status(text)
        except Exception as e:  # The tray must never break syncing
            logger.debug(f"Status callback failed: {e}")

    def _pause(self, reason: str) -> None:
        self.paused_reason = reason
        self._paused_at = self._clock()
        self._resume_requested.clear()
        logger.warning(f"Sync queue paused ({reason}); {self.queue.qsize()} item(s) kept")
        print(f"⏸️  Sync paused: {PAUSE_STATUS_TEXT.get(reason, reason)}")
        self._set_status(PAUSE_STATUS_TEXT.get(reason, reason))

    def request_resume(self) -> None:
        """Ask a paused queue to try again now (e.g. the user triggered a sync).

        Safe to call from any thread.
        """
        self._resume_requested.set()

    async def _maybe_resume(self) -> bool:
        """Resume a paused queue if its condition has cleared. Returns True if running."""
        reason = self.paused_reason
        if reason is None:
            return True

        requested = self._resume_requested.is_set()
        if reason == PAUSED_QUOTA:
            due = self._clock() - self._paused_at >= self.QUOTA_RECHECK_SECONDS
            if not (requested or due):
                return False
        elif reason == PAUSED_SIGN_IN:
            signed_in = self.cloud_sync.authenticated and bool(self.config.api.token)
            if not signed_in:
                return False

        self.paused_reason = None
        self._resume_requested.clear()
        logger.info(f"Sync queue resumed (was paused: {reason})")
        print("▶️  Sync resumed")
        self._set_status("Watching")

        if reason == PAUSED_SIGN_IN and self.on_reconnect is not None:
            try:
                await self.on_reconnect()
            except Exception as e:
                logger.warning(f"Rescan after sign-in failed: {e}", exc_info=True)
        return True

    # ------------------------------------------------------------------
    # Debounce
    # ------------------------------------------------------------------

    async def add(self, file_path: Path, notebook_uuid: str, file_type: str) -> bool:
        """
        Note a changed file. It is queued once no further change to the same path
        has been seen for ``sync.cooldown_seconds`` (trailing debounce).

        Safe to call from any thread (the watchdog thread calls it).

        Args:
            file_path: Path to the file
            notebook_uuid: Notebook UUID
            file_type: File type (rm, metadata, content, etc.)

        Returns:
            True (the change is always kept)
        """
        item = SyncItem(
            file_path=file_path,
            notebook_uuid=notebook_uuid,
            file_type=file_type,
            added_at=datetime.now(),
        )
        with self._pending_lock:
            restarted = str(file_path) in self._pending
            self._pending[str(file_path)] = (item, self._clock())

        if restarted:
            logger.debug(f"Debounce restarted for {file_path.name}")
        else:
            logger.info(f"Change noted: {file_path.name} (type={file_type}, uuid={notebook_uuid[:8]}...)")
            print(f"📝 Queued for sync: {file_path.name}")
        return True

    def _flush_due(self) -> int:
        """Move debounced paths that have been quiet long enough into the queue."""
        now = self._clock()
        cooldown = self.config.sync.cooldown_seconds
        with self._pending_lock:
            due_keys = [key for key, (_, seen) in self._pending.items() if now - seen >= cooldown]
            due = [self._pending.pop(key)[0] for key in due_keys]
        for item in due:
            self.queue.put_nowait(item)
        return len(due)

    def _requeue(self, items: list[SyncItem]) -> None:
        for item in items:
            self.queue.put_nowait(item)

    def _take_batch(self) -> list[SyncItem]:
        items: list[SyncItem] = []
        while len(items) < self.config.sync.batch_size:
            try:
                items.append(self.queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        return items

    # ------------------------------------------------------------------
    # Processing
    # ------------------------------------------------------------------

    async def _process_batch(self, items: list[SyncItem]) -> dict:
        """
        Process a batch of sync items using two-phase sync.

        Phase 1: Sync metadata for notebooks with .rm files (fast)
        Phase 2: Upload file content (slow, with OCR)

        Items whose content matches the manifest are skipped. On a rate limit,
        quota or sign-in error the current item and the rest of the batch are
        put back into the queue.

        Args:
            items: List of sync items to process

        Returns:
            Statistics about the batch processing
        """
        logger.info(f"Processing batch of {len(items)} items")

        stats = {
            "uploaded": 0,
            "failed": 0,
            "retried": 0,
            "skipped": 0,
            "requeued": 0,
        }

        # Drop files that are unchanged since their last upload (or baseline)
        to_upload = []
        for item in items:
            try:
                fingerprint = await asyncio.to_thread(self.manifest.changed_fingerprint, item.file_path)
            except OSError as e:
                logger.warning(f"Cannot read {item.file_path}, dropping it: {e}")
                stats["failed"] += 1
                continue
            if fingerprint is None:
                logger.debug(f"Unchanged since last upload, skipping: {item.file_path.name}")
                stats["skipped"] += 1
                continue
            to_upload.append((item, fingerprint))

        # Group by notebook for efficient processing
        notebooks: dict[str, list] = defaultdict(list)
        for item, fingerprint in to_upload:
            notebooks[item.notebook_uuid].append((item, fingerprint))

        logger.debug(f"Batch contains {len(notebooks)} notebooks")

        # Phase 1: Sync metadata for notebooks that have .rm files
        # This ensures the notebook structure exists before uploading content
        notebooks_with_rm = [
            uuid for uuid, entries in notebooks.items()
            if any(item.file_type == "rm" for item, _ in entries)
        ]

        if notebooks_with_rm:
            logger.info(f"Phase 1: Syncing metadata for {len(notebooks_with_rm)} notebook(s)")
            try:
                await self.metadata_sync.run(notebooks_with_rm)
            except Exception as e:
                logger.warning(f"Metadata sync failed (continuing with content upload): {e}")
                print(f"⚠️  Metadata sync failed: {e}")

        # Phase 2: Process each notebook's files
        ordered = [entry for entries in notebooks.values() for entry in entries]
        current_notebook = None
        for index, (item, fingerprint) in enumerate(ordered):
            if item.notebook_uuid != current_notebook:
                current_notebook = item.notebook_uuid
                count = len(notebooks[current_notebook])
                logger.info(f"Syncing {count} files for notebook {current_notebook[:8]}...")
                print(f"\n📤 Syncing {count} files for notebook {current_notebook[:8]}...")

            logger.debug(f"Processing item: {item.file_path.name} (type={item.file_type})")
            rest = [entry[0] for entry in ordered[index:]]
            backoff = 2

            while True:
                try:
                    result = await self.cloud_sync.upload_file(
                        item.file_path,
                        item.notebook_uuid,
                        item.file_type,
                    )
                except RateLimitError as e:
                    wait = min(e.retry_after, self.MAX_RATE_LIMIT_WAIT_SECONDS)
                    self._requeue(rest)
                    stats["requeued"] += len(rest)
                    logger.warning(f"Rate limited; {len(rest)} item(s) put back, waiting {wait}s")
                    print(f"⏳ Rate limited, waiting {wait}s before continuing...")
                    await self._sleep(wait)
                    return stats
                except QuotaExceededError:
                    self._requeue(rest)
                    stats["requeued"] += len(rest)
                    self._pause(PAUSED_QUOTA)
                    return stats
                except AuthenticationRequiredError as e:
                    logger.warning(f"Sign-in required: {e}")
                    self._requeue(rest)
                    stats["requeued"] += len(rest)
                    self._pause(PAUSED_SIGN_IN)
                    return stats
                except CloudSyncError as e:
                    if e.transient:
                        stats["retried"] += 1
                        logger.warning(
                            f"Upload of {item.file_path.name} failed ({e}); retrying in {backoff}s"
                        )
                        print(f"⚠️  Upload failed, retrying in {backoff}s...")
                        await self._sleep(backoff)
                        backoff = min(backoff * 2, self.MAX_BACKOFF_SECONDS)
                        continue
                    logger.error(f"Upload of {item.file_path.name} rejected, dropping it: {e}")
                    print(f"✗ Upload failed: {e}")
                    stats["failed"] += 1
                    break

                if _should_record(result):
                    await asyncio.to_thread(self.manifest.record_upload, item.file_path, fingerprint)
                stats["uploaded"] += 1
                logger.info(f"Successfully uploaded {item.file_path.name}")
                break

        logger.info(f"Batch processing complete: {stats}")
        return stats

    async def _run_once(self) -> dict | None:
        """One worker step: flush debounced paths, honour a pause, process one batch.

        Returns the batch stats, or None if nothing was processed.
        """
        self._flush_due()

        if not await self._maybe_resume():
            return None

        items = self._take_batch()
        if not items:
            return None

        stats = await self._process_batch(items)
        logger.info(
            f"Batch complete: {stats['uploaded']} uploaded, {stats['skipped']} unchanged, "
            f"{stats['failed']} failed, {stats['retried']} retried, {stats['requeued']} put back"
        )
        print(
            f"\n✓ Batch complete: {stats['uploaded']} uploaded, "
            f"{stats['failed']} failed, {stats['retried']} retried\n"
        )
        return stats

    async def _worker(self) -> None:
        """Background worker to process the sync queue."""
        logger.info("Sync queue worker started")
        print("Sync queue worker started")

        while self.running:
            try:
                stats = await self._run_once()
                if stats is None:
                    idle = self.PAUSED_POLL_SECONDS if self.paused_reason else self.IDLE_POLL_SECONDS
                    await self._sleep(idle)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"Error in sync queue worker: {e}", exc_info=True)
                print(f"Error in sync queue worker: {e}")
                await self._sleep(5)  # Wait before retrying

        logger.info("Sync queue worker stopped")
        print("Sync queue worker stopped")

    async def start(self) -> None:
        """Start the sync queue worker."""
        if self.running:
            return

        self.running = True
        self.worker_task = asyncio.create_task(self._worker())
        print("Sync queue started")

    async def stop(self) -> None:
        """Stop the sync queue worker.

        Items still waiting are not uploaded here (a retry loop could keep quit
        waiting indefinitely); they differ from the manifest, so the start-up
        rescan picks them up next time.
        """
        if not self.running:
            return

        print("Stopping sync queue...")
        self.running = False

        if self.worker_task:
            self.worker_task.cancel()
            try:
                await self.worker_task
            except asyncio.CancelledError:
                pass

        with self._pending_lock:
            waiting = len(self._pending)
        waiting += self.queue.qsize()
        if waiting:
            logger.info(f"{waiting} change(s) not uploaded yet; they will be picked up on next start")
            print(f"{waiting} change(s) will be uploaded on next start")

        print("Sync queue stopped")

    def get_stats(self) -> dict:
        """Get queue statistics."""
        with self._pending_lock:
            pending = len(self._pending)
        return {
            "queue_size": self.queue.qsize(),
            "pending": pending,
            "running": self.running,
            "paused_reason": self.paused_reason,
        }
