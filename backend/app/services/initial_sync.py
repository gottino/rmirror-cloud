"""Initial sync service for triggering first sync when integration is connected."""

import hashlib
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional

import httpx
from sqlalchemy.orm import Session

from app.models.notebook import Notebook
from app.models.notebook_page import NotebookPage
from app.models.page import OcrStatus, Page
from app.models.sync_record import IntegrationConfig, SyncQueue, SyncRecord

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

    The sync happens in two phases:
    1. Create notebook pages in Notion (sequentially, to prevent duplicates)
    2. Queue individual pages for background processing

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
        - notebooks_created: Number of notebook pages created in Notion
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

    # PHASE 1: Create notebook pages in Notion first (sequentially)
    # This prevents race conditions when workers process pages in parallel
    notebooks_created = 0
    if target_name == "notion":
        notebooks_created = await _create_notebook_pages_in_notion(
            db, user_id, target_name, pages_data
        )

    # PHASE 2: Queue individual pages for sync
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
        "notebooks_created": notebooks_created,
    }

    logger.info(
        f"Initial sync for user {user_id} to {target_name}: "
        f"notebooks created {notebooks_created}, queued {queued_count}, "
        f"skipped {skipped_count}, total {total_pages}"
    )

    return result


async def _create_notebook_pages_in_notion(
    db: Session,
    user_id: int,
    target_name: str,
    pages_data: list,
) -> int:
    """
    Create Notion pages for all unique notebooks before queuing pages.

    This prevents race conditions where multiple workers try to create
    the same notebook page simultaneously.

    Args:
        db: Database session
        user_id: User ID
        target_name: Target name (should be "notion")
        pages_data: List of (Page, NotebookPage, Notebook) tuples

    Returns:
        Number of notebook pages created in Notion
    """
    # Get integration config
    config = (
        db.query(IntegrationConfig)
        .filter(
            IntegrationConfig.user_id == user_id,
            IntegrationConfig.target_name == target_name,
            IntegrationConfig.is_enabled == True,
        )
        .first()
    )

    if not config:
        logger.warning(f"No active {target_name} integration for user {user_id}")
        return 0

    config_dict = config.get_config()
    access_token = config_dict.get("access_token")
    database_id = config_dict.get("database_id")

    if not access_token or not database_id:
        logger.warning(f"Missing Notion credentials for user {user_id}")
        return 0

    # Collect unique notebooks
    notebooks_to_create: Dict[str, Notebook] = {}
    for page, notebook_page, notebook in pages_data:
        if notebook.notebook_uuid not in notebooks_to_create:
            # Check if notebook already has a SyncRecord
            existing = (
                db.query(SyncRecord)
                .filter(
                    SyncRecord.user_id == user_id,
                    SyncRecord.notebook_uuid == notebook.notebook_uuid,
                    SyncRecord.item_type == "notebook",
                    SyncRecord.target_name == target_name,
                )
                .first()
            )
            if not existing:
                notebooks_to_create[notebook.notebook_uuid] = notebook

    if not notebooks_to_create:
        logger.info(f"All notebooks already have SyncRecords for user {user_id}")
        return 0

    logger.info(f"Creating {len(notebooks_to_create)} notebook pages in Notion for user {user_id}")

    created_count = 0
    for notebook_uuid, notebook in notebooks_to_create.items():
        try:
            # Create notebook page in Notion using direct HTTP call
            notion_page_id = await _create_notion_notebook_page(
                access_token=access_token,
                database_id=database_id,
                notebook=notebook,
            )

            if notion_page_id:
                # Create SyncRecord for this notebook
                sync_record = SyncRecord(
                    user_id=user_id,
                    target_name=target_name,
                    item_type="notebook",
                    item_id=str(notebook.id),
                    external_id=notion_page_id,
                    content_hash="notebook",
                    status="success",
                    synced_at=datetime.utcnow(),
                    notebook_uuid=notebook_uuid,
                )
                db.add(sync_record)
                db.commit()
                created_count += 1
                logger.info(f"📒 Created notebook '{notebook.visible_name}' -> {notion_page_id}")

        except Exception as e:
            logger.error(f"Failed to create notebook {notebook_uuid} in Notion: {e}")
            # Continue with other notebooks

    return created_count


async def _create_notion_notebook_page(
    access_token: str,
    database_id: str,
    notebook: Notebook,
) -> Optional[str]:
    """
    Create a notebook page in Notion.

    Args:
        access_token: Notion OAuth access token
        database_id: Notion database ID
        notebook: Notebook model

    Returns:
        Notion page ID if successful, None otherwise
    """
    # Build page properties
    properties = {
        "Name": {"title": [{"text": {"content": notebook.visible_name or "Untitled"}}]},
        "UUID": {"rich_text": [{"text": {"content": notebook.notebook_uuid}}]},
        "Path": {"rich_text": [{"text": {"content": ""}}]},  # Can be populated later
        "Pages": {"number": 0},  # Will be updated as pages are synced
        "Synced At": {"date": {"start": datetime.utcnow().isoformat()}},
        "Status": {"select": {"name": "Syncing"}},
    }

    # Add heading block for content
    children = [
        {
            "object": "block",
            "type": "heading_2",
            "heading_2": {
                "rich_text": [{"type": "text", "text": {"content": "Notebook Content"}}]
            },
        }
    ]

    # Create page using direct HTTP (works reliably with API 2022-06-28)
    response = httpx.post(
        "https://api.notion.com/v1/pages",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json",
        },
        json={
            "parent": {"database_id": database_id},
            "properties": properties,
            "children": children,
        },
        verify=False,
        timeout=30.0,
    )

    if response.status_code == 200:
        return response.json().get("id")
    else:
        logger.error(f"Notion API error: {response.status_code} - {response.text[:200]}")
        return None


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
