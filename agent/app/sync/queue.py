"""
Sync queue for batching and deduplicating file uploads.

Uses two-phase sync architecture:
1. Sync metadata for notebook (fast, creates structure)
2. Upload page content (slow, with OCR)
"""

import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from app.config import Config
from app.sync.cloud_sync import CloudSync, CloudSyncError
from app.sync.metadata_sync import MetadataSync

logger = logging.getLogger(__name__)


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


class SyncQueue:
    """
    Queue for managing file uploads to the cloud.

    Features:
    - Deduplication based on file path and notebook UUID
    - Cooldown period to prevent duplicate uploads
    - Batch processing for efficiency
    - Automatic retry on failures
    """

    def __init__(self, config: Config, cloud_sync: CloudSync):
        """Initialize sync queue."""
        self.config = config
        self.cloud_sync = cloud_sync
        self.metadata_sync = MetadataSync(config, cloud_sync)

        self.queue: asyncio.Queue[SyncItem] = asyncio.Queue()
        self.recent_syncs: dict[tuple[str, str], datetime] = {}  # (file_path, uuid) -> timestamp
        self.running = False
        self.worker_task: Optional[asyncio.Task] = None

    def should_sync(self, file_path: Path, notebook_uuid: str) -> bool:
        """
        Check if a file should be synced based on cooldown period.

        Args:
            file_path: Path to the file
            notebook_uuid: Notebook UUID

        Returns:
            True if file should be synced, False if in cooldown period
        """
        key = (str(file_path), notebook_uuid)
        if key not in self.recent_syncs:
            return True

        last_sync = self.recent_syncs[key]
        cooldown = timedelta(seconds=self.config.sync.cooldown_seconds)

        return datetime.now() - last_sync > cooldown

    async def add(self, file_path: Path, notebook_uuid: str, file_type: str) -> bool:
        """
        Add a file to the sync queue.

        Args:
            file_path: Path to the file
            notebook_uuid: Notebook UUID
            file_type: File type (rm, metadata, content, etc.)

        Returns:
            True if added, False if skipped due to cooldown
        """
        # Check cooldown
        if not self.should_sync(file_path, notebook_uuid):
            logger.debug(f"Skipping {file_path.name} (cooldown period)")
            print(f"⏭  Skipping {file_path.name} (cooldown period)")
            return False

        # Add to queue
        item = SyncItem(
            file_path=file_path,
            notebook_uuid=notebook_uuid,
            file_type=file_type,
            added_at=datetime.now(),
        )

        await self.queue.put(item)
        logger.info(f"Queued for sync: {file_path.name} (type={file_type}, uuid={notebook_uuid[:8]}...)")
        print(f"📝 Queued for sync: {file_path.name}")

        # Update recent syncs
        key = (str(file_path), notebook_uuid)
        self.recent_syncs[key] = datetime.now()

        return True

    async def _process_batch(self, items: list[SyncItem]) -> dict:
        """
        Process a batch of sync items using two-phase sync.

        Phase 1: Sync metadata for notebooks with .rm files (fast)
        Phase 2: Upload file content (slow, with OCR)

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
        }

        # Group by notebook for efficient processing
        notebooks: dict[str, list[SyncItem]] = defaultdict(list)
        for item in items:
            notebooks[item.notebook_uuid].append(item)

        logger.debug(f"Batch contains {len(notebooks)} notebooks")

        # Phase 1: Sync metadata for notebooks that have .rm files
        # This ensures the notebook structure exists before uploading content
        notebooks_with_rm = [
            uuid for uuid, items in notebooks.items()
            if any(item.file_type == "rm" for item in items)
        ]

        if notebooks_with_rm:
            logger.info(f"Phase 1: Syncing metadata for {len(notebooks_with_rm)} notebook(s)")
            try:
                await self.metadata_sync.run(notebooks_with_rm)
            except Exception as e:
                logger.warning(f"Metadata sync failed (continuing with content upload): {e}")
                print(f"⚠️  Metadata sync failed: {e}")

        # Phase 2: Process each notebook's files
        for notebook_uuid, notebook_items in notebooks.items():
            logger.info(f"Syncing {len(notebook_items)} files for notebook {notebook_uuid[:8]}...")
            print(f"\n📤 Syncing {len(notebook_items)} files for notebook {notebook_uuid[:8]}...")

            for item in notebook_items:
                logger.debug(f"Processing item: {item.file_path.name} (type={item.file_type})")
                retry_count = 0
                success = False

                while retry_count <= self.config.sync.retry_attempts and not success:
                    try:
                        logger.debug(f"Upload attempt {retry_count + 1} for {item.file_path.name}")

                        await self.cloud_sync.upload_file(
                            item.file_path,
                            item.notebook_uuid,
                            item.file_type,
                        )

                        stats["uploaded"] += 1
                        success = True
                        logger.info(f"Successfully uploaded {item.file_path.name}")

                    except CloudSyncError as e:
                        retry_count += 1
                        logger.warning(
                            f"Upload failed for {item.file_path.name} (attempt {retry_count}): {e}",
                            exc_info=retry_count > self.config.sync.retry_attempts
                        )

                        if retry_count <= self.config.sync.retry_attempts:
                            backoff_time = 2 ** retry_count
                            logger.info(f"Retrying in {backoff_time}s ({retry_count}/{self.config.sync.retry_attempts})...")
                            print(f"⚠️  Upload failed, retrying ({retry_count}/{self.config.sync.retry_attempts})...")
                            stats["retried"] += 1
                            await asyncio.sleep(backoff_time)  # Exponential backoff
                        else:
                            logger.error(f"Upload failed after {self.config.sync.retry_attempts} retries: {e}")
                            print(f"✗ Upload failed after {self.config.sync.retry_attempts} retries: {e}")
                            stats["failed"] += 1

            # OCR is triggered automatically by /v1/processing/rm-file endpoint
            # No need to trigger separately
            # if stats["uploaded"] > 0:
            #     try:
            #         await self.cloud_sync.trigger_ocr(notebook_uuid)
            #     except CloudSyncError as e:
            #         print(f"⚠️  OCR trigger failed: {e}")

        logger.info(f"Batch processing complete: {stats}")
        return stats

    async def _worker(self) -> None:
        """Background worker to process the sync queue."""
        logger.info("Sync queue worker started")
        print("Sync queue worker started")

        while self.running:
            try:
                # Collect items for batch processing
                items: list[SyncItem] = []
                batch_size = self.config.sync.batch_size

                # Wait for at least one item
                try:
                    logger.debug(f"Waiting for items (timeout={self.config.sync.sync_interval}s)...")
                    item = await asyncio.wait_for(
                        self.queue.get(),
                        timeout=self.config.sync.sync_interval,
                    )
                    items.append(item)
                    logger.debug(f"Got item from queue: {item.file_path.name}")
                except asyncio.TimeoutError:
                    # No items in queue, continue waiting
                    logger.debug("No items in queue, continuing to wait")
                    continue

                # Collect more items up to batch size (non-blocking)
                while len(items) < batch_size and not self.queue.empty():
                    try:
                        item = self.queue.get_nowait()
                        items.append(item)
                        logger.debug(f"Added to batch: {item.file_path.name}")
                    except asyncio.QueueEmpty:
                        break

                # Process the batch
                if items:
                    logger.info(f"Processing batch of {len(items)} items")
                    stats = await self._process_batch(items)
                    logger.info(
                        f"Batch complete: {stats['uploaded']} uploaded, "
                        f"{stats['failed']} failed, {stats['retried']} retried"
                    )
                    print(
                        f"\n✓ Batch complete: {stats['uploaded']} uploaded, "
                        f"{stats['failed']} failed, {stats['retried']} retried\n"
                    )

            except Exception as e:
                logger.error(f"Error in sync queue worker: {e}", exc_info=True)
                print(f"Error in sync queue worker: {e}")
                await asyncio.sleep(5)  # Wait before retrying

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
        """Stop the sync queue worker."""
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

        # Process remaining items
        remaining = []
        while not self.queue.empty():
            try:
                item = self.queue.get_nowait()
                remaining.append(item)
            except asyncio.QueueEmpty:
                break

        if remaining:
            print(f"Processing {len(remaining)} remaining items...")
            await self._process_batch(remaining)

        print("Sync queue stopped")

    def get_stats(self) -> dict:
        """Get queue statistics."""
        return {
            "queue_size": self.queue.qsize(),
            "recent_syncs": len(self.recent_syncs),
            "running": self.running,
        }
