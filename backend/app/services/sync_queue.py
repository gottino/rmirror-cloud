"""Sync queue management for background sync operations.

Provides functions to queue sync operations when OCR completes or catch-up sync is needed.
"""

import json
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.core.sync_engine import ContentFingerprint
from app.integrations.registry import NOTEBOOK_METADATA, PAGE_TEXT, TODO, targets_supporting
from app.models.notebook import Notebook
from app.models.sync_record import IntegrationConfig, SyncQueue, SyncRecord
from app.services.fingerprinting import fingerprint_highlight, fingerprint_page, fingerprint_todo


def queue_sync(
    db: Session,
    user_id: int,
    item_type: str,
    item_id: str,
    content_hash: str,
    target_name: str,
    page_uuid: Optional[str] = None,
    notebook_uuid: Optional[str] = None,
    page_number: Optional[int] = None,
    priority: int = 5,
    metadata: Optional[dict] = None,
) -> SyncQueue:
    """
    Queue an item for sync to an external service.

    Called when:
    - OCR completes on a page
    - A todo is extracted
    - A highlight is created
    - Catch-up sync is triggered

    Args:
        db: Database session
        user_id: User ID
        item_type: Type of item ('page_text', 'todo', 'highlight', 'notebook_metadata')
        item_id: ID of the item to sync
        content_hash: Content hash for deduplication
        target_name: Target service ('notion', 'readwise', etc.)
        page_uuid: Optional reMarkable page UUID
        notebook_uuid: Optional notebook UUID
        page_number: Optional page number
        priority: Queue priority (1-10, lower = higher priority)
        metadata: Optional metadata dict

    Returns:
        Created SyncQueue entry

    Example:
        >>> queue_entry = queue_sync(
        ...     db=db,
        ...     user_id=42,
        ...     item_type='page_text',
        ...     item_id='123',
        ...     content_hash='abc123...',
        ...     target_name='notion',
        ...     page_uuid='page-uuid',
        ...     notebook_uuid='notebook-uuid',
        ...     page_number=5
        ... )
    """
    import json

    # For page_text items, check by page_uuid (reMarkable's unique page identifier)
    # This ensures we update existing pages rather than creating duplicates
    if item_type == 'page_text' and page_uuid:
        # Check if already queued for this specific page. Only a 'pending' row can
        # still absorb new content; a 'processing' row keeps the content it
        # started with, so changed content gets its own new pending row below.
        existing_queue = (
            db.query(SyncQueue)
            .filter(
                SyncQueue.page_uuid == page_uuid,
                SyncQueue.target_name == target_name,
                SyncQueue.user_id == user_id,
                SyncQueue.status == 'pending',
            )
            .first()
        )

        if existing_queue:
            # Already queued for this page, update content hash if changed
            if existing_queue.content_hash != content_hash:
                existing_queue.content_hash = content_hash
                existing_queue.updated_at = datetime.utcnow()
                if existing_queue.status == 'pending' and existing_queue.retry_count:
                    # New content deserves a fresh attempt, not the tail end of
                    # the old content's backoff.
                    existing_queue.retry_count = 0
                    existing_queue.scheduled_at = datetime.utcnow()
                db.commit()
            return existing_queue

        # Check if already successfully synced with same content
        existing_sync = (
            db.query(SyncRecord)
            .filter(
                SyncRecord.page_uuid == page_uuid,
                SyncRecord.target_name == target_name,
                SyncRecord.user_id == user_id,
            )
            .first()
        )

        if existing_sync and existing_sync.content_hash == content_hash:
            # Already synced successfully with same content, no need to queue
            # Create a completed queue entry for tracking
            queue_entry = SyncQueue(
                user_id=user_id,
                item_type=item_type,
                item_id=item_id,
                content_hash=content_hash,
                page_uuid=page_uuid,
                notebook_uuid=notebook_uuid,
                page_number=page_number,
                target_name=target_name,
                status='completed',
                priority=priority,
                metadata_json=json.dumps(metadata) if metadata else None,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                completed_at=existing_sync.synced_at,
            )
            db.add(queue_entry)
            db.commit()
            return queue_entry
        # If existing_sync exists but content_hash is different, we'll queue it for update
    else:
        # For other item types, use content_hash for deduplication
        existing_queue = (
            db.query(SyncQueue)
            .filter(
                SyncQueue.content_hash == content_hash,
                SyncQueue.target_name == target_name,
                SyncQueue.user_id == user_id,
                SyncQueue.status.in_(['pending', 'processing']),
            )
            .first()
        )

        if existing_queue:
            # Already queued, don't create duplicate
            return existing_queue

        # Check if already successfully synced
        existing_sync = (
            db.query(SyncRecord)
            .filter(
                SyncRecord.content_hash == content_hash,
                SyncRecord.target_name == target_name,
                SyncRecord.user_id == user_id,
                SyncRecord.status == 'success',
            )
            .first()
        )

        if existing_sync:
            # Already synced successfully, no need to queue
            # Create a completed queue entry for tracking
            queue_entry = SyncQueue(
                user_id=user_id,
                item_type=item_type,
                item_id=item_id,
                content_hash=content_hash,
                page_uuid=page_uuid,
                notebook_uuid=notebook_uuid,
                page_number=page_number,
                target_name=target_name,
                status='completed',
                priority=priority,
                metadata_json=json.dumps(metadata) if metadata else None,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                completed_at=existing_sync.synced_at,
            )
            db.add(queue_entry)
            db.commit()
            return queue_entry

    # Create new queue entry
    queue_entry = SyncQueue(
        user_id=user_id,
        item_type=item_type,
        item_id=item_id,
        content_hash=content_hash,
        page_uuid=page_uuid,
        notebook_uuid=notebook_uuid,
        page_number=page_number,
        target_name=target_name,
        status='pending',
        priority=priority,
        metadata_json=json.dumps(metadata) if metadata else None,
        scheduled_at=datetime.utcnow(),  # Process ASAP
    )

    db.add(queue_entry)
    db.commit()
    db.refresh(queue_entry)

    return queue_entry


def queue_page_sync(
    db: Session,
    user_id: int,
    page_id: int,
    notebook_uuid: str,
    page_number: int,
    ocr_text: str,
    page_uuid: Optional[str] = None,
) -> list[SyncQueue]:
    """
    Queue page sync to all enabled notebook integrations.

    Called when OCR completes for a page.
    Only queues to integrations that support page text (notion, etc.).
    Does NOT queue to todo-only integrations (notion-todos, todoist).

    Args:
        db: Database session
        user_id: User ID
        page_id: Page database ID
        notebook_uuid: Notebook UUID
        page_number: Page number
        ocr_text: OCR-extracted text
        page_uuid: Optional reMarkable page UUID

    Returns:
        List of created SyncQueue entries

    Example:
        >>> queued = queue_page_sync(
        ...     db=db,
        ...     user_id=42,
        ...     page_id=123,
        ...     notebook_uuid='notebook-uuid',
        ...     page_number=5,
        ...     ocr_text='Meeting notes...'
        ... )
    """
    # Generate content hash
    content_hash = fingerprint_page(notebook_uuid, page_number, ocr_text, page_uuid)

    # Get all enabled integrations that accept page text (target registry)
    integrations = (
        db.query(IntegrationConfig)
        .filter(
            IntegrationConfig.user_id == user_id,
            IntegrationConfig.is_enabled == True,
            IntegrationConfig.target_name.in_(targets_supporting(PAGE_TEXT)),
        )
        .all()
    )

    queued_entries = []
    for integration in integrations:
        queue_entry = queue_sync(
            db=db,
            user_id=user_id,
            item_type='page_text',
            item_id=str(page_id),
            content_hash=content_hash,
            target_name=integration.target_name,
            page_uuid=page_uuid,
            notebook_uuid=notebook_uuid,
            page_number=page_number,
            priority=3,  # Higher priority for fresh content
        )
        queued_entries.append(queue_entry)

    return queued_entries


def queue_todo_sync(
    db: Session,
    user_id: int,
    todo_id: int,
    todo_text: str,
    notebook_uuid: str,
    page_number: Optional[int] = None,
    page_uuid: Optional[str] = None,
) -> list[SyncQueue]:
    """
    Queue todo sync to all enabled todo-specific integrations.

    Only queues to integrations that support todos (notion-todos, todoist).
    Does NOT queue to general notebook integrations (notion).

    Args:
        db: Database session
        user_id: User ID
        todo_id: Todo database ID
        todo_text: Todo text content
        notebook_uuid: Notebook UUID
        page_number: Optional page number
        page_uuid: Optional reMarkable page UUID

    Returns:
        List of created SyncQueue entries
    """
    # Generate content hash and fuzzy signature
    content_hash, _ = fingerprint_todo(todo_text, notebook_uuid, page_number)

    # Get all enabled integrations that accept todos (target registry)
    integrations = (
        db.query(IntegrationConfig)
        .filter(
            IntegrationConfig.user_id == user_id,
            IntegrationConfig.is_enabled == True,
            IntegrationConfig.target_name.in_(targets_supporting(TODO)),
        )
        .all()
    )

    queued_entries = []
    for integration in integrations:
        queue_entry = queue_sync(
            db=db,
            user_id=user_id,
            item_type='todo',
            item_id=str(todo_id),
            content_hash=content_hash,
            target_name=integration.target_name,
            page_uuid=page_uuid,
            notebook_uuid=notebook_uuid,
            page_number=page_number,
            priority=2,  # Higher priority for todos
        )
        queued_entries.append(queue_entry)

    return queued_entries


def _page_count_from_content(content_json: Optional[str]) -> int:
    """Page count from a notebook's .content data (pageCount, else its page list)."""
    if not content_json:
        return 0
    try:
        content_data = json.loads(content_json)
    except (TypeError, ValueError):
        return 0
    if not isinstance(content_data, dict):
        return 0
    page_count = content_data.get("pageCount")
    if isinstance(page_count, int):
        return page_count
    pages = content_data.get("pages") or (content_data.get("cPages") or {}).get("pages") or []
    return len(pages) if isinstance(pages, list) else 0


def notebook_metadata_payload(notebook: Notebook) -> dict:
    """Properties-only data for a notebook_metadata sync (no page content)."""
    # reMarkable's own lastModified (ms since epoch); notebook.updated_at changes
    # on every database write, so it is not used here.
    last_modified_at = None
    if notebook.metadata_json:
        try:
            meta = json.loads(notebook.metadata_json)
            if meta.get("lastModified"):
                last_modified_at = datetime.fromtimestamp(
                    int(meta["lastModified"]) / 1000.0
                ).isoformat()
        except (ValueError, KeyError, TypeError, AttributeError):
            pass

    title = notebook.visible_name or "Untitled Notebook"
    return {
        "notebook_uuid": notebook.notebook_uuid,
        "notebook_name": title,
        "title": title,
        "page_count": _page_count_from_content(notebook.content_json),
        "full_path": notebook.full_path or "",
        "last_opened_at": notebook.last_opened.isoformat() if notebook.last_opened else None,
        "last_modified_at": last_modified_at,
    }


def queue_notebook_metadata_sync(db: Session, notebook: Notebook) -> list[SyncQueue]:
    """Queue a properties-only update of the notebook for every target that accepts one.

    The worker rebuilds the payload from the database when it runs, so a row
    always writes the notebook's latest metadata. Rows are deduplicated by the
    metadata's content hash (see queue_sync).
    """
    content_hash = ContentFingerprint.for_notebook_metadata(notebook_metadata_payload(notebook))

    integrations = (
        db.query(IntegrationConfig)
        .filter(
            IntegrationConfig.user_id == notebook.user_id,
            IntegrationConfig.is_enabled == True,  # noqa: E712
            IntegrationConfig.target_name.in_(targets_supporting(NOTEBOOK_METADATA)),
        )
        .all()
    )

    return [
        queue_sync(
            db=db,
            user_id=notebook.user_id,
            item_type=NOTEBOOK_METADATA,
            item_id=notebook.notebook_uuid,
            content_hash=content_hash,
            target_name=integration.target_name,
            notebook_uuid=notebook.notebook_uuid,
            priority=5,
        )
        for integration in integrations
    ]


def queue_highlight_sync(
    db: Session,
    user_id: int,
    highlight_id: int,
    original_text: str,
    corrected_text: str,
    source_file: str,
    page_num: int,
    notebook_uuid: Optional[str] = None,
    page_uuid: Optional[str] = None,
) -> list[SyncQueue]:
    """
    Queue highlight sync to all enabled integrations.

    Args:
        db: Database session
        user_id: User ID
        highlight_id: Highlight database ID
        original_text: Original highlighted text
        corrected_text: User-corrected text
        source_file: Source file identifier
        page_num: Page number
        notebook_uuid: Optional notebook UUID
        page_uuid: Optional reMarkable page UUID

    Returns:
        List of created SyncQueue entries
    """
    # Generate content hash
    content_hash = fingerprint_highlight(original_text, corrected_text, source_file, page_num)

    # Get all enabled integrations
    integrations = (
        db.query(IntegrationConfig)
        .filter(
            IntegrationConfig.user_id == user_id,
            IntegrationConfig.is_enabled == True,
        )
        .all()
    )

    queued_entries = []
    for integration in integrations:
        queue_entry = queue_sync(
            db=db,
            user_id=user_id,
            item_type='highlight',
            item_id=str(highlight_id),
            content_hash=content_hash,
            target_name=integration.target_name,
            page_uuid=page_uuid,
            notebook_uuid=notebook_uuid,
            page_number=page_num,
            priority=4,  # Normal priority
        )
        queued_entries.append(queue_entry)

    return queued_entries


def get_next_sync_items(db: Session, limit: int = 10) -> list[SyncQueue]:
    """
    Get next items to sync from the queue.

    Returns items in priority order that are ready to process.

    Args:
        db: Database session
        limit: Maximum number of items to return

    Returns:
        List of SyncQueue entries ready for processing

    Example:
        >>> items = get_next_sync_items(db, limit=5)
        >>> for item in items:
        ...     # Process sync
        ...     item.status = 'processing'
        ...     db.commit()
    """
    now = datetime.utcnow()

    return (
        db.query(SyncQueue)
        .filter(
            SyncQueue.status == 'pending',
            SyncQueue.scheduled_at <= now,
        )
        .order_by(
            SyncQueue.priority.asc(),  # Lower number = higher priority
            SyncQueue.created_at.asc(),  # FIFO within same priority
        )
        .limit(limit)
        .all()
    )
