"""API endpoints for sync operations."""

import json
import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from app.auth.clerk import get_clerk_active_user
from app.core.sync_engine import SyncItem
from app.core.unified_sync_manager import UnifiedSyncManager
from app.database import get_db
from app.integrations.notion_sync import NotionSyncTarget
from app.models.notebook import Notebook
from app.models.notebook_page import NotebookPage
from app.models.page import OcrStatus, Page
from app.models.sync_record import IntegrationConfig, SyncItemType, SyncQueue, SyncRecord
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter(tags=["sync"])

# Rate limiter for sync endpoints
limiter = Limiter(key_func=get_remote_address)


class SyncRequest(BaseModel):
    """Request to trigger a sync operation."""

    target_name: str  # "notion", "readwise", "all"
    item_type: str | None = None  # "notebook", "todo", "highlight" or None for all
    limit: int = 100
    notebook_uuids: list[str] | None = None  # Optional list of specific notebook UUIDs to sync


class SyncResponse(BaseModel):
    """Response from a sync operation."""

    success: bool
    message: str
    synced_count: int
    failed_count: int
    skipped_count: int


class SyncStatsResponse(BaseModel):
    """Sync statistics response."""

    target_name: str
    total_records: int
    status_counts: dict
    target_counts: dict
    type_counts: dict


# ============================================================================
# Metadata Sync Models (Two-Phase Sync Architecture)
# ============================================================================


class NotebookMetadataItem(BaseModel):
    """Metadata for a single notebook to sync."""

    uuid: str = Field(..., description="reMarkable notebook UUID")
    visible_name: str = Field(..., description="Display name of the notebook")
    parent_uuid: Optional[str] = Field(None, description="Parent folder UUID, if any")
    document_type: str = Field("notebook", description="Document type (notebook, pdf, epub, folder)")
    pages: List[str] = Field(default_factory=list, description="Ordered list of page UUIDs from .content file")
    # Optional metadata fields
    pinned: Optional[bool] = None
    deleted: Optional[bool] = None
    version: Optional[int] = None
    last_opened: Optional[str] = None
    last_opened_page: Optional[int] = None


class MetadataSyncRequest(BaseModel):
    """Request to sync notebook metadata and page structure.

    This is Phase 1 of the two-phase sync architecture:
    - Fast: Creates notebook records and page stubs (no OCR, no file uploads)
    - Establishes structure immediately so users see their content right away
    - Dashboard shows pages as "Not synced" until content is uploaded
    """

    notebooks: List[NotebookMetadataItem] = Field(
        ..., description="List of notebooks with their page structure"
    )


class MetadataSyncResponse(BaseModel):
    """Response from metadata sync operation."""

    success: bool
    notebooks_created: int = Field(..., description="Number of new notebooks created")
    notebooks_updated: int = Field(..., description="Number of existing notebooks updated")
    pages_registered: int = Field(..., description="Total number of page stubs registered")
    pages_already_synced: int = Field(..., description="Pages that already have content")
    message: str


@router.post("/metadata", response_model=MetadataSyncResponse)
@limiter.limit("100/minute")  # Higher limit for lightweight metadata sync
async def sync_metadata(
    request: Request,
    sync_request: MetadataSyncRequest,
    current_user: User = Depends(get_clerk_active_user),
    db: Session = Depends(get_db),
):
    """
    Sync notebook metadata and page structure (Phase 1 of two-phase sync).

    This endpoint:
    1. Creates or updates Notebook records with metadata
    2. Creates Page stubs with NOT_SYNCED status for each page UUID
    3. Creates NotebookPage mappings to establish page order

    The result is that users immediately see their notebook structure in the
    dashboard, with pages shown as "Not synced" until content is uploaded.

    This is designed to be fast (no file processing, no OCR) and can handle
    many notebooks in a single request.

    Args:
        sync_request: List of notebooks with their page UUIDs
        current_user: Authenticated user
        db: Database session

    Returns:
        MetadataSyncResponse with counts of created/updated items
    """
    logger.info(
        f"Metadata sync started for user {current_user.id}: "
        f"{len(sync_request.notebooks)} notebooks"
    )

    notebooks_created = 0
    notebooks_updated = 0
    pages_registered = 0
    pages_already_synced = 0

    try:
        for nb_data in sync_request.notebooks:
            # Find or create notebook
            notebook = db.query(Notebook).filter(
                Notebook.user_id == current_user.id,
                Notebook.notebook_uuid == nb_data.uuid
            ).first()

            if notebook:
                # Update existing notebook metadata
                notebook.visible_name = nb_data.visible_name
                notebook.parent_uuid = nb_data.parent_uuid
                if nb_data.pinned is not None:
                    notebook.pinned = nb_data.pinned
                if nb_data.deleted is not None:
                    notebook.deleted = nb_data.deleted
                if nb_data.version is not None:
                    notebook.version = nb_data.version
                if nb_data.last_opened:
                    try:
                        notebook.last_opened = datetime.fromisoformat(nb_data.last_opened.replace("Z", "+00:00"))
                    except ValueError:
                        pass
                if nb_data.last_opened_page is not None:
                    notebook.last_opened_page = nb_data.last_opened_page
                notebook.last_synced_at = datetime.utcnow()
                notebooks_updated += 1
                logger.debug(f"Updated notebook: {nb_data.visible_name} ({nb_data.uuid})")
            else:
                # Create new notebook
                notebook = Notebook(
                    user_id=current_user.id,
                    notebook_uuid=nb_data.uuid,
                    visible_name=nb_data.visible_name,
                    parent_uuid=nb_data.parent_uuid,
                    document_type=nb_data.document_type,
                    pinned=nb_data.pinned or False,
                    deleted=nb_data.deleted or False,
                    version=nb_data.version,
                    last_synced_at=datetime.utcnow(),
                )
                if nb_data.last_opened:
                    try:
                        notebook.last_opened = datetime.fromisoformat(nb_data.last_opened.replace("Z", "+00:00"))
                    except ValueError:
                        pass
                if nb_data.last_opened_page is not None:
                    notebook.last_opened_page = nb_data.last_opened_page
                db.add(notebook)
                db.flush()  # Get the notebook ID
                notebooks_created += 1
                logger.debug(f"Created notebook: {nb_data.visible_name} ({nb_data.uuid})")

            # Store page UUIDs in content_json for reference
            if nb_data.pages:
                content_data = {
                    "pages": nb_data.pages,
                    "pageCount": len(nb_data.pages),
                }
                notebook.content_json = json.dumps(content_data)

            # Process page stubs
            for page_idx, page_uuid in enumerate(nb_data.pages):
                # Find existing page
                page = db.query(Page).filter(
                    Page.notebook_id == notebook.id,
                    Page.page_uuid == page_uuid
                ).first()

                if page and page.s3_key:
                    # Page already has content uploaded - don't reset it
                    pages_already_synced += 1
                elif page:
                    # Page exists but no content - ensure NOT_SYNCED status
                    if page.ocr_status not in [OcrStatus.COMPLETED, OcrStatus.PENDING, OcrStatus.PROCESSING]:
                        page.ocr_status = OcrStatus.NOT_SYNCED
                    pages_registered += 1
                else:
                    # Create new page stub
                    page = Page(
                        notebook_id=notebook.id,
                        page_uuid=page_uuid,
                        ocr_status=OcrStatus.NOT_SYNCED,
                    )
                    db.add(page)
                    db.flush()  # Get the page ID
                    pages_registered += 1

                # Create or update NotebookPage mapping
                page_number = page_idx + 1  # 1-indexed
                notebook_page = db.query(NotebookPage).filter(
                    NotebookPage.notebook_id == notebook.id,
                    NotebookPage.page_id == page.id
                ).first()

                if notebook_page:
                    # Update page order if changed
                    notebook_page.page_number = page_number
                else:
                    # Create new mapping
                    notebook_page = NotebookPage(
                        notebook_id=notebook.id,
                        page_id=page.id,
                        page_number=page_number,
                    )
                    db.add(notebook_page)

        db.commit()

        total_pages = pages_registered + pages_already_synced
        logger.info(
            f"Metadata sync completed for user {current_user.id}: "
            f"{notebooks_created} created, {notebooks_updated} updated, "
            f"{pages_registered} new page stubs, {pages_already_synced} already synced"
        )

        return MetadataSyncResponse(
            success=True,
            notebooks_created=notebooks_created,
            notebooks_updated=notebooks_updated,
            pages_registered=pages_registered,
            pages_already_synced=pages_already_synced,
            message=f"Synced {notebooks_created + notebooks_updated} notebooks with {total_pages} pages",
        )

    except Exception as e:
        db.rollback()
        logger.error(f"Metadata sync failed for user {current_user.id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Metadata sync failed: {str(e)}"
        )


@router.post("/trigger", response_model=SyncResponse)
async def trigger_sync(
    request: SyncRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_clerk_active_user),
    db: Session = Depends(get_db),
):
    """
    Trigger a sync operation.

    This will sync content to the specified target (or all targets if "all" is specified).
    The sync runs in the background.
    """
    try:
        # Initialize sync manager
        sync_manager = UnifiedSyncManager(db, current_user.id)

        # Get integration configs for the user
        if request.target_name == "all":
            configs = (
                db.query(IntegrationConfig)
                .filter(
                    IntegrationConfig.user_id == current_user.id,
                    IntegrationConfig.is_enabled == True,
                )
                .all()
            )
        else:
            config = (
                db.query(IntegrationConfig)
                .filter(
                    IntegrationConfig.user_id == current_user.id,
                    IntegrationConfig.target_name == request.target_name,
                    IntegrationConfig.is_enabled == True,
                )
                .first()
            )

            if not config:
                raise HTTPException(
                    status_code=404,
                    detail=f"Integration '{request.target_name}' not found or disabled",
                )

            configs = [config]

        if not configs:
            raise HTTPException(
                status_code=404, detail="No enabled integrations found"
            )

        # Register sync targets
        for config in configs:
            config_dict = json.loads(config.config_json)

            if config.target_name == "notion":
                target = NotionSyncTarget(
                    api_token=config_dict.get("api_token"),
                    database_id=config_dict.get("database_id"),
                )
                sync_manager.register_target(target)

        # Start sync in background
        background_tasks.add_task(
            _run_sync,
            sync_manager,
            request.target_name,
            request.limit,
            current_user.id,
            db,
            request.notebook_uuids,
        )

        return SyncResponse(
            success=True,
            message=f"Sync started for {request.target_name}",
            synced_count=0,
            failed_count=0,
            skipped_count=0,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error triggering sync: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


async def _run_sync(
    sync_manager: UnifiedSyncManager,
    target_name: str,
    limit: int,
    user_id: int,
    db: Session,
    notebook_uuids: list[str] | None = None,
):
    """
    Run sync operation in background.

    Args:
        sync_manager: Initialized sync manager
        target_name: Target to sync to
        limit: Maximum items to sync
        user_id: User ID
        db: Database session
        notebook_uuids: Optional list of specific notebook UUIDs to sync
    """
    try:
        logger.info(f"Starting background sync for user {user_id} to {target_name}")

        synced_count = 0
        failed_count = 0
        skipped_count = 0

        # Get targets to sync to
        if target_name == "all":
            target_names = list(sync_manager.targets.keys())
        else:
            target_names = [target_name]

        # Get notebooks needing sync
        for t_name in target_names:
            if notebook_uuids:
                # Sync specific notebooks
                notebooks = sync_manager.get_specific_notebooks(t_name, notebook_uuids)
            else:
                # Sync notebooks that need syncing
                notebooks = sync_manager.get_notebooks_needing_sync(t_name, limit)

            logger.info(f"Found {len(notebooks)} notebooks to sync to {t_name}")

            for notebook_item in notebooks:
                result = await sync_manager.sync_item_to_target(notebook_item, t_name)

                if result.success:
                    synced_count += 1
                elif result.status.value == "skipped":
                    skipped_count += 1
                else:
                    failed_count += 1

            # Update last_synced_at
            config = (
                db.query(IntegrationConfig)
                .filter(
                    IntegrationConfig.user_id == user_id,
                    IntegrationConfig.target_name == t_name,
                )
                .first()
            )
            if config:
                config.last_synced_at = datetime.utcnow()
                db.commit()

        logger.info(
            f"Background sync completed: {synced_count} synced, {failed_count} failed, {skipped_count} skipped"
        )

    except Exception as e:
        logger.error(f"Error in background sync: {e}", exc_info=True)


@router.get("/stats", response_model=SyncStatsResponse)
async def get_sync_stats(
    target_name: str | None = None,
    current_user: User = Depends(get_clerk_active_user),
    db: Session = Depends(get_db),
):
    """
    Get sync statistics.

    Returns statistics about sync operations for the current user.
    """
    try:
        sync_manager = UnifiedSyncManager(db, current_user.id)
        stats = sync_manager.get_sync_stats(target_name)

        return SyncStatsResponse(
            target_name=stats.get("target_name", "all"),
            total_records=stats.get("total_records", 0),
            status_counts=stats.get("status_counts", {}),
            target_counts=stats.get("target_counts", {}),
            type_counts=stats.get("type_counts", {}),
        )

    except Exception as e:
        logger.error(f"Error getting sync stats: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status/{target_name}")
async def get_sync_status(
    target_name: str,
    current_user: User = Depends(get_clerk_active_user),
    db: Session = Depends(get_db),
):
    """
    Get detailed sync status for a specific target.

    Returns information about recent sync operations and any errors.
    """
    try:
        sync_manager = UnifiedSyncManager(db, current_user.id)
        stats = sync_manager.get_sync_stats(target_name)

        # Get integration config
        config = (
            db.query(IntegrationConfig)
            .filter(
                IntegrationConfig.user_id == current_user.id,
                IntegrationConfig.target_name == target_name,
            )
            .first()
        )

        if not config:
            raise HTTPException(
                status_code=404, detail=f"Integration '{target_name}' not found"
            )

        return {
            "target_name": target_name,
            "is_enabled": config.is_enabled,
            "last_synced_at": config.last_synced_at.isoformat()
            if config.last_synced_at
            else None,
            "stats": stats,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting sync status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/process-queue")
async def process_sync_queue(
    limit: int = 10,
    current_user: User = Depends(get_clerk_active_user),
    db: Session = Depends(get_db),
):
    """
    Process pending items in the sync queue.

    This endpoint manually processes items from the sync queue.
    In production, this would be handled by a background worker.
    """
    try:
        # Get pending queue items for this user
        pending_items = (
            db.query(SyncQueue)
            .filter(
                SyncQueue.user_id == current_user.id,
                SyncQueue.status == 'pending',
            )
            .order_by(SyncQueue.priority, SyncQueue.created_at)
            .limit(limit)
            .all()
        )

        if not pending_items:
            return {
                "success": True,
                "message": "No pending items in queue",
                "processed": 0,
                "failed": 0
            }

        logger.info(f"Processing {len(pending_items)} pending sync items")

        processed = 0
        failed = 0

        for queue_item in pending_items:
            try:
                # Mark as processing
                queue_item.status = 'processing'
                queue_item.retry_count += 1
                queue_item.started_at = datetime.utcnow()
                db.commit()

                # Get integration config
                config = (
                    db.query(IntegrationConfig)
                    .filter(
                        IntegrationConfig.user_id == current_user.id,
                        IntegrationConfig.target_name == queue_item.target_name,
                        IntegrationConfig.is_enabled == True,
                    )
                    .first()
                )

                if not config:
                    logger.warning(f"No active integration found for {queue_item.target_name}")
                    queue_item.status = 'failed'
                    queue_item.error_message = f"Integration {queue_item.target_name} not active"
                    failed += 1
                    db.commit()
                    continue

                # Get the page data
                if queue_item.item_type == 'page_text':
                    page = db.query(Page).filter(Page.id == int(queue_item.item_id)).first()
                    if not page:
                        logger.warning(f"Page {queue_item.item_id} not found")
                        queue_item.status = 'failed'
                        queue_item.error_message = "Page not found"
                        failed += 1
                        db.commit()
                        continue

                    # Get notebook info
                    notebook = db.query(Notebook).filter(Notebook.id == page.notebook_id).first()

                    # Get decrypted config
                    config_dict = config.get_config()

                    # Create appropriate sync target
                    if queue_item.target_name == 'notion':
                        from app.integrations.notion_sync import NotionSyncTarget
                        target = NotionSyncTarget(
                            access_token=config_dict.get('access_token'),
                            database_id=config_dict.get('database_id'),
                        )
                    else:
                        logger.warning(f"Unknown target: {queue_item.target_name}")
                        queue_item.status = 'failed'
                        queue_item.error_message = f"Unknown target: {queue_item.target_name}"
                        failed += 1
                        db.commit()
                        continue

                    # Create sync item
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
                            **metadata
                        },
                        source_table='pages',
                        created_at=page.created_at,
                        updated_at=page.updated_at,
                    )

                    # Sync the item
                    result = await target.sync_item(sync_item)

                    if result.success:
                        # Create sync record
                        sync_record = SyncRecord(
                            user_id=current_user.id,
                            target_name=queue_item.target_name,
                            item_type=queue_item.item_type,
                            item_id=queue_item.item_id,
                            content_hash=queue_item.content_hash,
                            external_id=result.target_id,
                            status='success',
                            synced_at=datetime.utcnow(),
                        )
                        db.add(sync_record)

                        # Mark queue item as completed
                        queue_item.status = 'completed'
                        queue_item.completed_at = datetime.utcnow()
                        processed += 1

                        logger.info(f"Successfully synced page {page.id} to {queue_item.target_name}")
                    else:
                        queue_item.status = 'failed'
                        queue_item.error_message = result.error_message
                        failed += 1
                        logger.error(f"Failed to sync page {page.id}: {result.error_message}")

                    db.commit()
                else:
                    logger.warning(f"Unsupported item type: {queue_item.item_type}")
                    queue_item.status = 'failed'
                    queue_item.error_message = f"Unsupported item type: {queue_item.item_type}"
                    failed += 1
                    db.commit()

            except Exception as e:
                logger.error(f"Error processing queue item {queue_item.id}: {e}", exc_info=True)
                queue_item.status = 'failed'
                queue_item.error_message = str(e)
                failed += 1
                db.commit()

        return {
            "success": True,
            "message": f"Processed {processed} items, {failed} failed",
            "processed": processed,
            "failed": failed
        }

    except Exception as e:
        logger.error(f"Error processing sync queue: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
