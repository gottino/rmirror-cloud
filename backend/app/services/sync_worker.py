"""Background worker for processing sync queue."""

import asyncio
import json
import logging
import time
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.core.sync_engine import SyncItem, SyncItemType
from app.database import SessionLocal
from app.integrations.notion_sync import NotionSyncTarget
from app.models.notebook import Notebook
from app.models.page import Page
from app.models.sync_record import IntegrationConfig, SyncQueue, SyncRecord

logger = logging.getLogger(__name__)


class SyncWorker:
    """Background worker that processes items from the sync queue."""

    def __init__(self, poll_interval: int = 5):
        """
        Initialize sync worker.

        Args:
            poll_interval: Seconds to wait between checking for new items (default: 5)
        """
        self.poll_interval = poll_interval
        self.running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self):
        """Start the background worker."""
        if self.running:
            logger.warning("Sync worker already running")
            return

        self.running = True
        self._task = asyncio.create_task(self._run())
        logger.info(f"🔄 Sync worker started (poll interval: {self.poll_interval}s)")

    async def stop(self):
        """Stop the background worker."""
        if not self.running:
            return

        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("🛑 Sync worker stopped")

    async def _run(self):
        """Main worker loop that polls the queue and processes items."""
        logger.info("Starting sync worker main loop")

        while self.running:
            try:
                # Process pending items
                await self._process_pending_items()

                # Wait before next poll
                await asyncio.sleep(self.poll_interval)

            except asyncio.CancelledError:
                logger.info("Sync worker cancelled")
                break
            except Exception as e:
                logger.error(f"Error in sync worker loop: {e}", exc_info=True)
                # Continue running even if there's an error
                await asyncio.sleep(self.poll_interval)

    async def _process_pending_items(self, limit: int = 10):
        """
        Process pending items from the queue.

        Args:
            limit: Maximum number of items to process in one batch
        """
        db: Session = SessionLocal()
        try:
            # Get pending items with row-level locking to prevent race conditions
            # FOR UPDATE SKIP LOCKED ensures each worker gets different items
            pending_items = (
                db.query(SyncQueue)
                .filter(
                    SyncQueue.status == 'pending',
                    SyncQueue.scheduled_at <= datetime.utcnow(),
                )
                .order_by(
                    SyncQueue.priority.asc(),  # Lower number = higher priority
                    SyncQueue.created_at.asc(),  # FIFO within same priority
                )
                .limit(limit)
                .with_for_update(skip_locked=True)
                .all()
            )

            if not pending_items:
                return

            logger.info(
                "Processing %d pending sync items",
                len(pending_items),
                extra={"event": "sync.batch", "batch_size": len(pending_items)},
            )

            # Mark all items as 'processing' immediately to prevent other workers
            # from picking them up (FOR UPDATE locks are released on commit)
            for item in pending_items:
                item.status = 'processing'
                item.started_at = datetime.utcnow()
            db.commit()

            for queue_item in pending_items:
                try:
                    await self._process_queue_item(db, queue_item)
                except Exception as e:
                    logger.error(
                        "Sync item failed",
                        exc_info=True,
                        extra={
                            "event": "sync.fail",
                            "queue_id": queue_item.id,
                            "target": queue_item.target_name,
                            "error": str(e),
                            "retry_count": queue_item.retry_count,
                        },
                    )
                    # Mark as failed
                    queue_item.status = 'failed'
                    queue_item.error_message = str(e)
                    queue_item.retry_count += 1
                    db.commit()

        finally:
            db.close()

    async def _process_queue_item(self, db: Session, queue_item: SyncQueue):
        """
        Process a single queue item.

        Args:
            db: Database session
            queue_item: Queue item to process
        """
        # Increment retry count (status already set to 'processing' by caller)
        queue_item.retry_count += 1
        _item_start = time.monotonic()

        logger.info(
            "Processing queue item %d: %s -> %s",
            queue_item.id,
            queue_item.item_type,
            queue_item.target_name,
            extra={
                "event": "sync.start",
                "queue_id": queue_item.id,
                "target": queue_item.target_name,
                "page_uuid": getattr(queue_item, "page_uuid", None),
                "notebook_uuid": getattr(queue_item, "notebook_uuid", None),
            },
        )

        # Get integration config
        config = (
            db.query(IntegrationConfig)
            .filter(
                IntegrationConfig.user_id == queue_item.user_id,
                IntegrationConfig.target_name == queue_item.target_name,
                IntegrationConfig.is_enabled == True,
            )
            .first()
        )

        if not config:
            logger.warning(
                f"No active integration found for {queue_item.target_name}"
            )
            queue_item.status = 'failed'
            queue_item.error_message = f"Integration {queue_item.target_name} not active"
            db.commit()
            return

        # Process based on item type
        if queue_item.item_type == 'page_text':
            await self._process_page_sync(db, queue_item, config, _item_start)
        else:
            logger.warning(f"Unsupported item type: {queue_item.item_type}")
            queue_item.status = 'failed'
            queue_item.error_message = f"Unsupported item type: {queue_item.item_type}"
            db.commit()

    async def _process_page_sync(
        self,
        db: Session,
        queue_item: SyncQueue,
        config: IntegrationConfig,
        _item_start: float = 0.0,
    ):
        """
        Process a page text sync.

        Args:
            db: Database session
            queue_item: Queue item
            config: Integration config
            _item_start: Monotonic start time for duration tracking
        """
        # Get the page data
        page = db.query(Page).filter(Page.id == int(queue_item.item_id)).first()
        if not page:
            logger.warning(f"Page {queue_item.item_id} not found")
            queue_item.status = 'failed'
            queue_item.error_message = "Page not found"
            db.commit()
            return

        # Get notebook info
        notebook = db.query(Notebook).filter(Notebook.id == page.notebook_id).first()

        # Get decrypted config
        config_dict = config.get_config()

        # Create appropriate sync target
        if queue_item.target_name == 'notion':
            target = NotionSyncTarget(
                access_token=config_dict.get('access_token'),
                database_id=config_dict.get('database_id'),
            )
        else:
            logger.warning(f"Unknown target: {queue_item.target_name}")
            queue_item.status = 'failed'
            queue_item.error_message = f"Unknown target: {queue_item.target_name}"
            db.commit()
            return

        # Check if the NOTEBOOK was previously synced to get the parent Notion page ID
        # This prevents creating multiple Notion pages for the same notebook
        notebook_record = (
            db.query(SyncRecord)
            .filter(
                SyncRecord.user_id == queue_item.user_id,
                SyncRecord.notebook_uuid == queue_item.notebook_uuid,
                SyncRecord.item_type == 'notebook',
                SyncRecord.target_name == queue_item.target_name,
            )
            .first()
        )

        existing_notebook_page_id = notebook_record.external_id if notebook_record else None

        # Check if this PAGE was previously synced to get the existing Notion block ID
        # Use page_uuid as the primary identifier (reMarkable's unique page ID)
        existing_record = (
            db.query(SyncRecord)
            .filter(
                SyncRecord.user_id == queue_item.user_id,
                SyncRecord.page_uuid == queue_item.page_uuid,
                SyncRecord.target_name == queue_item.target_name,
            )
            .first()
        )

        existing_block_id = existing_record.external_id if existing_record else None
        existing_content_hash = existing_record.content_hash if existing_record else None

        # Check if content actually changed
        content_changed = existing_content_hash != queue_item.content_hash

        if existing_record and not content_changed:
            # Content unchanged, skip sync
            logger.info(f"⏭️ Page {queue_item.page_number} unchanged, skipping Notion sync")
            queue_item.status = 'completed'
            queue_item.completed_at = datetime.utcnow()
            db.commit()
            return

        # Create sync item with existing IDs if available
        metadata = json.loads(queue_item.metadata_json) if queue_item.metadata_json else {}
        sync_item = SyncItem(
            item_type=SyncItemType.PAGE_TEXT,
            item_id=str(page.id),
            content_hash=queue_item.content_hash,
            data={
                'page_uuid': queue_item.page_uuid,
                'notebook_uuid': queue_item.notebook_uuid,
                'page_number': queue_item.page_number,
                'text': page.ocr_text or '',
                'notebook_name': notebook.visible_name if notebook else 'Unknown',
                'existing_block_id': existing_block_id,  # Pass existing page block ID
                'existing_notebook_page_id': existing_notebook_page_id,  # Pass existing notebook page ID
                'user_id': queue_item.user_id,
                **metadata
            },
            source_table='pages',
            created_at=page.created_at,
            updated_at=page.updated_at,
        )

        # Sync the item
        result = await target.sync_item(sync_item)

        if result.success:
            # Check if sync record already exists (upsert pattern)
            # Use page_uuid (reMarkable's unique page identifier), not content_hash
            # since content_hash changes when page content changes
            existing_record = (
                db.query(SyncRecord)
                .filter(
                    SyncRecord.user_id == queue_item.user_id,
                    SyncRecord.page_uuid == queue_item.page_uuid,
                    SyncRecord.target_name == queue_item.target_name,
                )
                .first()
            )

            if existing_record:
                # Update existing record with new content hash and block ID
                existing_record.external_id = result.target_id
                existing_record.content_hash = queue_item.content_hash
                existing_record.status = 'success'
                existing_record.synced_at = datetime.utcnow()
                existing_record.updated_at = datetime.utcnow()
                logger.info(f"Updated existing sync record for page {page.id}")
            else:
                # Create new sync record
                sync_record = SyncRecord(
                    user_id=queue_item.user_id,
                    target_name=queue_item.target_name,
                    item_type=queue_item.item_type,
                    item_id=queue_item.item_id,
                    content_hash=queue_item.content_hash,
                    external_id=result.target_id,
                    status='success',
                    synced_at=datetime.utcnow(),
                    page_uuid=queue_item.page_uuid,
                    notebook_uuid=queue_item.notebook_uuid,
                    page_number=queue_item.page_number,
                )
                db.add(sync_record)

            # If a new notebook page was created in Notion, also create a SyncRecord for it
            # This prevents duplicate notebook pages on future syncs
            result_metadata = result.metadata or {}
            if result_metadata.get('notebook_created') and result_metadata.get('notebook_page_id'):
                notebook_page_id = result_metadata['notebook_page_id']
                # Check if notebook SyncRecord already exists (shouldn't happen but be safe)
                existing_notebook_record = (
                    db.query(SyncRecord)
                    .filter(
                        SyncRecord.user_id == queue_item.user_id,
                        SyncRecord.notebook_uuid == queue_item.notebook_uuid,
                        SyncRecord.item_type == 'notebook',
                        SyncRecord.target_name == queue_item.target_name,
                    )
                    .first()
                )
                if not existing_notebook_record:
                    notebook_sync_record = SyncRecord(
                        user_id=queue_item.user_id,
                        target_name=queue_item.target_name,
                        item_type='notebook',
                        item_id=str(notebook.id) if notebook else '',
                        external_id=notebook_page_id,
                        content_hash='notebook',  # Placeholder - notebooks don't have content hash
                        status='success',
                        synced_at=datetime.utcnow(),
                        notebook_uuid=queue_item.notebook_uuid,
                    )
                    db.add(notebook_sync_record)
                    logger.info(
                        f"📒 Created notebook sync record for {queue_item.notebook_uuid} "
                        f"-> Notion page {notebook_page_id}"
                    )

            # Mark queue item as completed
            queue_item.status = 'completed'
            queue_item.completed_at = datetime.utcnow()

            duration_ms = round((time.monotonic() - _item_start) * 1000, 1)
            logger.info(
                "Sync item completed: page %d -> %s",
                page.id,
                queue_item.target_name,
                extra={
                    "event": "sync.done",
                    "queue_id": queue_item.id,
                    "target": queue_item.target_name,
                    "duration_ms": duration_ms,
                    "page_uuid": queue_item.page_uuid,
                    "notebook_uuid": queue_item.notebook_uuid,
                },
            )
        else:
            duration_ms = round((time.monotonic() - _item_start) * 1000, 1)
            queue_item.status = 'failed'
            queue_item.error_message = result.error_message
            logger.error(
                "Sync item failed: page %d: %s",
                page.id,
                result.error_message,
                extra={
                    "event": "sync.fail",
                    "queue_id": queue_item.id,
                    "target": queue_item.target_name,
                    "duration_ms": duration_ms,
                    "error": result.error_message,
                },
            )

        db.commit()


# Global worker instance
_worker: Optional[SyncWorker] = None


async def start_sync_worker(poll_interval: int = 5):
    """
    Start the global sync worker.

    Args:
        poll_interval: Seconds to wait between checking for new items
    """
    global _worker

    if _worker is not None:
        logger.warning("Sync worker already exists")
        return

    _worker = SyncWorker(poll_interval=poll_interval)
    await _worker.start()


async def stop_sync_worker():
    """Stop the global sync worker."""
    global _worker

    if _worker is None:
        return

    await _worker.stop()
    _worker = None
