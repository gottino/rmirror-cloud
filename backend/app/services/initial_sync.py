"""Initial sync service for triggering first sync when integration is connected."""

import hashlib
import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.models.notebook import Notebook
from app.models.notebook_page import NotebookPage
from app.models.page import OcrStatus, Page
from app.models.sync_record import SyncQueue, SyncRecord

logger = logging.getLogger(__name__)

# Rate limiting configuration
# Notion has a rate limit of ~3 requests/second average
# We'll be conservative and schedule items with spacing to avoid hitting limits
ITEMS_PER_BATCH = 10  # Items to schedule at the same time
BATCH_INTERVAL_SECONDS = 5  # Seconds between batches
INITIAL_SYNC_PRIORITY = 8  # Lower priority than real-time syncs (5)


async def trigger_initial_sync(
    db: Session,
    user_id: int,
    target_name: str,
    max_items: Optional[int] = None,
) -> dict:
    """
    Queue all existing OCR-completed pages for sync to a target.

    This is called when a user first connects an integration (e.g., Notion)
    to sync their existing data to the new target.

    Args:
        db: Database session
        user_id: User ID
        target_name: Target integration name (e.g., "notion")
        max_items: Maximum number of items to queue (None for all)

    Returns:
        Dictionary with sync statistics:
        - queued_count: Number of items queued
        - skipped_count: Number of items skipped (already synced or no content)
        - total_pages: Total pages found for user
    """
    logger.info(f"Triggering initial sync for user {user_id} to {target_name}")

    # Get all pages with completed OCR for this user
    # Join through notebook to get user's pages
    pages_query = (
        db.query(Page, NotebookPage, Notebook)
        .join(NotebookPage, Page.id == NotebookPage.page_id)
        .join(Notebook, NotebookPage.notebook_id == Notebook.id)
        .filter(
            Notebook.user_id == user_id,
            Notebook.deleted == False,
            Page.ocr_status == OcrStatus.COMPLETED.value,
            Page.ocr_text.isnot(None),
            Page.ocr_text != "",
        )
        .order_by(
            # Most recently opened notebooks first, then highest page numbers first
            Notebook.last_opened.desc().nullslast(),
            NotebookPage.page_number.desc(),
        )
    )

    if max_items:
        pages_query = pages_query.limit(max_items)

    pages_data = pages_query.all()
    total_pages = len(pages_data)

    logger.info(f"Found {total_pages} pages with completed OCR for user {user_id}")

    queued_count = 0
    skipped_count = 0
    current_time = datetime.utcnow()

    for idx, (page, notebook_page, notebook) in enumerate(pages_data):
        # Check if already synced to this target
        existing_record = (
            db.query(SyncRecord)
            .filter(
                SyncRecord.user_id == user_id,
                SyncRecord.page_uuid == page.page_uuid,
                SyncRecord.target_name == target_name,
            )
            .first()
        )

        if existing_record:
            # Skip if already synced (content hash check will be done by worker)
            skipped_count += 1
            continue

        # Check if already queued (pending or processing)
        existing_queue = (
            db.query(SyncQueue)
            .filter(
                SyncQueue.user_id == user_id,
                SyncQueue.item_id == str(page.id),
                SyncQueue.target_name == target_name,
                SyncQueue.status.in_(["pending", "processing"]),
            )
            .first()
        )

        if existing_queue:
            skipped_count += 1
            continue

        # Calculate content hash for deduplication
        content_hash = _calculate_content_hash(page.ocr_text or "")

        # Calculate scheduled time with staggered batches
        batch_number = idx // ITEMS_PER_BATCH
        scheduled_at = current_time + timedelta(seconds=batch_number * BATCH_INTERVAL_SECONDS)

        # Create queue entry
        queue_item = SyncQueue(
            user_id=user_id,
            item_type="page_text",
            item_id=str(page.id),
            content_hash=content_hash,
            page_uuid=page.page_uuid,
            notebook_uuid=notebook.notebook_uuid,
            page_number=notebook_page.page_number,
            target_name=target_name,
            status="pending",
            priority=INITIAL_SYNC_PRIORITY,
            scheduled_at=scheduled_at,
        )
        db.add(queue_item)
        queued_count += 1

    db.commit()

    result = {
        "queued_count": queued_count,
        "skipped_count": skipped_count,
        "total_pages": total_pages,
    }

    logger.info(
        f"Initial sync for user {user_id} to {target_name}: "
        f"queued {queued_count}, skipped {skipped_count}, total {total_pages}"
    )

    return result


def _calculate_content_hash(text: str) -> str:
    """Calculate SHA-256 hash of content for deduplication."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


async def get_initial_sync_status(
    db: Session,
    user_id: int,
    target_name: str,
) -> dict:
    """
    Get the status of an initial sync operation.

    Args:
        db: Database session
        user_id: User ID
        target_name: Target integration name

    Returns:
        Dictionary with status:
        - pending_count: Items still pending in queue
        - processing_count: Items currently being processed
        - completed_count: Items successfully synced
        - failed_count: Items that failed to sync
        - total_synced: Total items synced to target (from sync_records)
    """
    # Queue status
    pending_count = (
        db.query(SyncQueue)
        .filter(
            SyncQueue.user_id == user_id,
            SyncQueue.target_name == target_name,
            SyncQueue.status == "pending",
            SyncQueue.priority == INITIAL_SYNC_PRIORITY,
        )
        .count()
    )

    processing_count = (
        db.query(SyncQueue)
        .filter(
            SyncQueue.user_id == user_id,
            SyncQueue.target_name == target_name,
            SyncQueue.status == "processing",
        )
        .count()
    )

    completed_count = (
        db.query(SyncQueue)
        .filter(
            SyncQueue.user_id == user_id,
            SyncQueue.target_name == target_name,
            SyncQueue.status == "completed",
            SyncQueue.priority == INITIAL_SYNC_PRIORITY,
        )
        .count()
    )

    failed_count = (
        db.query(SyncQueue)
        .filter(
            SyncQueue.user_id == user_id,
            SyncQueue.target_name == target_name,
            SyncQueue.status == "failed",
            SyncQueue.priority == INITIAL_SYNC_PRIORITY,
        )
        .count()
    )

    # Total synced records
    total_synced = (
        db.query(SyncRecord)
        .filter(
            SyncRecord.user_id == user_id,
            SyncRecord.target_name == target_name,
            SyncRecord.status == "success",
        )
        .count()
    )

    return {
        "pending_count": pending_count,
        "processing_count": processing_count,
        "completed_count": completed_count,
        "failed_count": failed_count,
        "total_synced": total_synced,
        "in_progress": pending_count > 0 or processing_count > 0,
    }
