"""Sync queue management for background sync operations.

Provides functions to queue sync operations when OCR completes or catch-up sync is needed.
"""

import json
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from app.core.sync_engine import ContentFingerprint
from app.integrations.registry import NOTEBOOK_METADATA, PAGE_TEXT, TODO, targets_supporting
from app.models.notebook import Notebook
from app.models.sync_record import IntegrationConfig, SyncQueue, SyncRecord
from app.services.fingerprinting import fingerprint_page, fingerprint_todo


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
) -> Optional[SyncQueue]:
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
        The pending or processing SyncQueue entry for this item, or None when
        the item is already synced with this content (nothing is queued).

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
            # Already synced with the same content: nothing to queue, and no
            # row is written (the sync record already says it is in sync).
            return None
        # If existing_sync exists but content_hash is different, we'll queue it for update
    elif item_type == NOTEBOOK_METADATA and notebook_uuid:
        # One pending row per notebook and target: the agent reports metadata on
        # every open, and the worker rebuilds the payload from the notebook when
        # it runs, so a pending row just takes the newest hash. Its retry
        # schedule is kept, so frequent opens do not defeat the backoff.
        existing_queue = (
            db.query(SyncQueue)
            .filter(
                SyncQueue.user_id == user_id,
                SyncQueue.target_name == target_name,
                SyncQueue.item_type == NOTEBOOK_METADATA,
                SyncQueue.notebook_uuid == notebook_uuid,
                SyncQueue.status == 'pending',
            )
            .first()
        )
        if existing_queue:
            if existing_queue.content_hash != content_hash:
                existing_queue.content_hash = content_hash
                existing_queue.updated_at = datetime.utcnow()
                db.commit()
            return existing_queue

        # The worker keeps one record per notebook and target with the hash it
        # last wrote; unchanged metadata is not queued again.
        existing_sync = (
            db.query(SyncRecord)
            .filter(
                SyncRecord.user_id == user_id,
                SyncRecord.target_name == target_name,
                SyncRecord.item_type == NOTEBOOK_METADATA,
                SyncRecord.notebook_uuid == notebook_uuid,
                SyncRecord.status == 'success',
            )
            .first()
        )
        if existing_sync and existing_sync.content_hash == content_hash:
            return None
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
            # Already synced successfully: nothing to queue, no row written.
            return None

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
        if queue_entry is not None:
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
        if queue_entry is not None:
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
    always writes the notebook's latest metadata. There is at most one pending
    row per notebook and target, and none when the target already has this
    metadata (see queue_sync). Makes no external calls.

    Returns the pending queue rows, new or reused.
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

    queued = []
    for integration in integrations:
        entry = queue_sync(
            db=db,
            user_id=notebook.user_id,
            item_type=NOTEBOOK_METADATA,
            item_id=notebook.notebook_uuid,
            content_hash=content_hash,
            target_name=integration.target_name,
            notebook_uuid=notebook.notebook_uuid,
            priority=5,
        )
        if entry is not None:
            queued.append(entry)
    return queued


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


def prune_sync_queue(
    db: Session,
    *,
    completed_days: int,
    failed_days: int,
    now: Optional[datetime] = None,
    batch_size: int = 500,
    max_batches: int = 10,
) -> int:
    """Delete finished queue rows older than their retention period.

    Only 'completed' rows (by ``completed_at``, falling back to
    ``updated_at``) and 'failed' rows (by ``updated_at``) are deleted; pending
    and processing rows are never touched. Deletes at most
    ``batch_size * max_batches`` rows per call, committing after each batch,
    so one run never holds a long lock. A retention of 0 or less disables
    pruning for that status.

    Returns the number of rows deleted.
    """
    now = now or datetime.utcnow()
    conditions = []
    if completed_days > 0:
        conditions.append(
            and_(
                SyncQueue.status == 'completed',
                func.coalesce(SyncQueue.completed_at, SyncQueue.updated_at)
                < now - timedelta(days=completed_days),
            )
        )
    if failed_days > 0:
        conditions.append(
            and_(
                SyncQueue.status == 'failed',
                SyncQueue.updated_at < now - timedelta(days=failed_days),
            )
        )

    deleted = 0
    for condition in conditions:
        for _ in range(max_batches):
            ids = [
                row.id
                for row in db.query(SyncQueue.id).filter(condition).limit(batch_size).all()
            ]
            if not ids:
                break
            db.query(SyncQueue).filter(SyncQueue.id.in_(ids)).delete(synchronize_session=False)
            db.commit()
            deleted += len(ids)
            if len(ids) < batch_size:
                break
    return deleted
