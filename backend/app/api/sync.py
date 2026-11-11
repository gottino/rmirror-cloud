"""API endpoints for sync operations."""

import json
import logging
from datetime import datetime
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import bindparam, func, insert, select, update
from sqlalchemy.orm import Session

from app.auth.clerk import get_clerk_active_user, get_clerk_session_user
from app.core.unified_sync_manager import UnifiedSyncManager
from app.database import get_db
from app.integrations.registry import PAGE_TEXT, missing_config, supports
from app.models.deleted_notebook import DeletedNotebook
from app.models.notebook import Notebook
from app.models.notebook_page import NotebookPage
from app.models.page import OcrStatus, Page
from app.models.sync_record import IntegrationConfig
from app.models.user import User
from app.services.initial_sync import queue_pages_for_sync
from app.utils.files import parse_uuid

logger = logging.getLogger(__name__)
router = APIRouter(tags=["sync"])

# Rate limiter for sync endpoints
limiter = Limiter(key_func=get_remote_address)


class SyncRequest(BaseModel):
    """Request to trigger a sync operation."""

    target_name: str  # a target that accepts page text (e.g. "notion"), or "all"
    item_type: str | None = None  # Ignored; kept so existing clients still validate
    limit: int = 100  # Ignored; every unsynced page is queued
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


# The agent sends its whole library in one request, and a large library can hold
# a few thousand notebooks. These caps sit well above that; they exist to reject
# absurd payloads, not to shape normal use.
MAX_METADATA_NOTEBOOKS = 5000
MAX_PAGES_PER_NOTEBOOK = 5000


class NotebookMetadataItem(BaseModel):
    """Metadata for a single notebook to sync."""

    uuid: str = Field(..., description="reMarkable notebook UUID")
    visible_name: str = Field(..., description="Display name of the notebook")
    parent_uuid: Optional[str] = Field(None, description="Parent folder UUID, if any")
    document_type: str = Field("notebook", description="Document type (notebook, pdf, epub, folder)")
    pages: List[str] = Field(
        default_factory=list,
        max_length=MAX_PAGES_PER_NOTEBOOK,
        description="Ordered list of page UUIDs from .content file",
    )
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
        ..., max_length=MAX_METADATA_NOTEBOOKS, description="List of notebooks with their page structure"
    )


class MetadataSyncResponse(BaseModel):
    """Response from metadata sync operation."""

    success: bool
    notebooks_created: int = Field(..., description="Number of new notebooks created")
    notebooks_updated: int = Field(..., description="Number of existing notebooks updated")
    pages_registered: int = Field(..., description="Total number of page stubs registered")
    pages_already_synced: int = Field(..., description="Pages that already have content")
    skipped: int = Field(0, description="Notebooks and pages skipped because their id was not a UUID")
    message: str


# Rows per IN (...) list, well below the bind-parameter limits of SQLite and PostgreSQL.
_IN_CHUNK = 1000

# Notebook columns the metadata sync updates only when the agent sent a value.
_OPTIONAL_NOTEBOOK_FIELDS = ("pinned", "deleted", "version", "last_opened", "last_opened_page", "content_json")


def _chunks(values: list, size: int = _IN_CHUNK):
    for i in range(0, len(values), size):
        yield values[i : i + size]


def _parse_last_opened(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _apply_metadata_sync(db: Session, user_id: int, entries: list) -> tuple[int, int, int, int]:
    """Upsert notebooks, page stubs and page order for a metadata sync in bulk.

    ``entries`` is a list of ``(notebook_uuid, NotebookMetadataItem, page_uuids)``
    with validated, lowercase UUIDs. Reads existing rows with a few IN queries
    and writes with multi-row INSERTs and executemany UPDATEs, so the number of
    statements does not grow with the number of notebooks or pages (apart from
    one extra statement per 1,000 ids in an IN list).

    Semantics match the former row-by-row version: a notebook or page seen
    again (in the database or earlier in the same request) is updated, pages
    that already have content are left alone, and pages without content that
    are not completed/pending/processing are reset to NOT_SYNCED.

    Returns (notebooks_created, notebooks_updated, pages_registered, pages_already_synced).
    """
    notebooks_created = notebooks_updated = pages_registered = pages_already_synced = 0
    now = datetime.utcnow()

    # 1. Existing notebooks (lowest id wins if a uuid is duplicated).
    notebook_ids: dict[str, int] = {}
    uuids = list(dict.fromkeys(nb_uuid for nb_uuid, _, _ in entries))
    for chunk in _chunks(uuids):
        rows = db.execute(
            select(Notebook.id, Notebook.notebook_uuid)
            .where(Notebook.user_id == user_id, Notebook.notebook_uuid.in_(chunk))
            .order_by(Notebook.id)
        ).all()
        for nb_id, nb_uuid in rows:
            notebook_ids.setdefault(nb_uuid, nb_id)
    existing_notebook_ids = list(notebook_ids.values())

    # 2. Fold the request into one insert row or one update per notebook.
    new_notebooks: dict[str, dict] = {}
    notebook_updates: dict[int, dict] = {}
    for nb_uuid, nb_data, page_uuids in entries:
        values = {
            "pinned": nb_data.pinned,
            "deleted": nb_data.deleted,
            "version": nb_data.version,
            "last_opened": _parse_last_opened(nb_data.last_opened),
            "last_opened_page": nb_data.last_opened_page,
            # Store page UUIDs in content_json for reference
            "content_json": (
                json.dumps({"pages": page_uuids, "pageCount": len(page_uuids)}) if page_uuids else None
            ),
        }
        if nb_uuid in notebook_ids or nb_uuid in new_notebooks:
            target = new_notebooks.get(nb_uuid)
            if target is None:
                target = notebook_updates.setdefault(
                    notebook_ids[nb_uuid], dict.fromkeys(_OPTIONAL_NOTEBOOK_FIELDS)
                )
            target["visible_name"] = nb_data.visible_name
            target["parent_uuid"] = nb_data.parent_uuid
            target["last_synced_at"] = now
            for field in _OPTIONAL_NOTEBOOK_FIELDS:
                if values[field] is not None:
                    target[field] = values[field]
            notebooks_updated += 1
            logger.debug(f"Updated notebook: {nb_data.visible_name} ({nb_uuid})")
        else:
            values["pinned"] = nb_data.pinned or False
            values["deleted"] = nb_data.deleted or False
            new_notebooks[nb_uuid] = {
                "user_id": user_id,
                "notebook_uuid": nb_uuid,
                "visible_name": nb_data.visible_name,
                "parent_uuid": nb_data.parent_uuid,
                "document_type": nb_data.document_type,
                "last_synced_at": now,
                **values,
            }
            notebooks_created += 1
            logger.debug(f"Created notebook: {nb_data.visible_name} ({nb_uuid})")

    if new_notebooks:
        result = db.execute(
            insert(Notebook).returning(Notebook.id, Notebook.notebook_uuid),
            list(new_notebooks.values()),
        )
        for nb_id, nb_uuid in result:
            notebook_ids[nb_uuid] = nb_id

    if notebook_updates:
        table = Notebook.__table__
        optional = {
            field: func.coalesce(bindparam(f"b_{field}", type_=table.c[field].type), table.c[field])
            for field in _OPTIONAL_NOTEBOOK_FIELDS
        }
        db.execute(
            update(table)
            .where(table.c.id == bindparam("b_id"))
            .values(
                visible_name=bindparam("b_visible_name"),
                parent_uuid=bindparam("b_parent_uuid"),
                last_synced_at=bindparam("b_last_synced_at"),
                **optional,
            ),
            [
                {"b_id": nb_id, **{f"b_{key}": value for key, value in values.items()}}
                for nb_id, values in notebook_updates.items()
            ],
        )

    # 3. Existing pages and page-order mappings of the existing notebooks.
    pages: dict[tuple[int, str], tuple[int, str | None, str]] = {}
    mappings: dict[tuple[int, int], tuple[int, int]] = {}
    for chunk in _chunks(existing_notebook_ids):
        page_rows = db.execute(
            select(Page.id, Page.notebook_id, Page.page_uuid, Page.s3_key, Page.ocr_status)
            .where(Page.notebook_id.in_(chunk))
            .order_by(Page.id)
        ).all()
        for page_id, nb_id, page_uuid, s3_key, ocr_status in page_rows:
            pages.setdefault((nb_id, page_uuid), (page_id, s3_key, ocr_status))
        mapping_rows = db.execute(
            select(NotebookPage.id, NotebookPage.notebook_id, NotebookPage.page_id, NotebookPage.page_number)
            .where(NotebookPage.notebook_id.in_(chunk))
            .order_by(NotebookPage.id)
        ).all()
        for mapping_id, nb_id, page_id, page_number in mapping_rows:
            mappings.setdefault((nb_id, page_id), (mapping_id, page_number))

    # 4. Page stubs: which to create, which to reset, and the wanted page order
    # (the last position wins if a page is listed twice).
    new_pages: dict[tuple[int, str], None] = {}
    reset_page_ids: set[int] = set()
    page_numbers: dict[tuple[int, str], int] = {}
    for nb_uuid, _, page_uuids in entries:
        nb_id = notebook_ids[nb_uuid]
        for page_idx, page_uuid in enumerate(page_uuids):
            key = (nb_id, page_uuid)
            page_numbers[key] = page_idx + 1  # 1-indexed
            page = pages.get(key)
            if page and page[1]:
                # Page already has content uploaded - don't reset it
                pages_already_synced += 1
            elif page:
                # Page exists but no content - ensure NOT_SYNCED status
                if page[2] not in (
                    OcrStatus.COMPLETED,
                    OcrStatus.PENDING,
                    OcrStatus.PROCESSING,
                    OcrStatus.NOT_SYNCED,
                ):
                    reset_page_ids.add(page[0])
                pages_registered += 1
            else:
                new_pages[key] = None
                pages_registered += 1

    if new_pages:
        result = db.execute(
            insert(Page).returning(Page.id, Page.notebook_id, Page.page_uuid),
            [
                {"notebook_id": nb_id, "page_uuid": page_uuid, "ocr_status": OcrStatus.NOT_SYNCED.value}
                for nb_id, page_uuid in new_pages
            ],
        )
        for page_id, nb_id, page_uuid in result:
            pages[(nb_id, page_uuid)] = (page_id, None, OcrStatus.NOT_SYNCED.value)

    for chunk in _chunks(sorted(reset_page_ids)):
        db.execute(
            update(Page).where(Page.id.in_(chunk)).values(ocr_status=OcrStatus.NOT_SYNCED.value),
            execution_options={"synchronize_session": False},
        )

    # 5. Create or update NotebookPage mappings.
    new_mappings = []
    mapping_updates = []
    for (nb_id, page_uuid), page_number in page_numbers.items():
        page_id = pages[(nb_id, page_uuid)][0]
        mapping = mappings.get((nb_id, page_id))
        if mapping is None:
            new_mappings.append({"notebook_id": nb_id, "page_id": page_id, "page_number": page_number})
        elif mapping[1] != page_number:
            mapping_updates.append({"id": mapping[0], "page_number": page_number})
    if mapping_updates:
        db.execute(update(NotebookPage), mapping_updates)
    if new_mappings:
        db.execute(insert(NotebookPage), new_mappings)

    return notebooks_created, notebooks_updated, pages_registered, pages_already_synced


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
    skipped = 0

    try:
        entries = []
        for nb_data in sync_request.notebooks:
            # Ids become storage keys later: skip anything that is not a UUID
            # instead of failing the whole batch. Never log the raw value.
            try:
                nb_uuid = parse_uuid(nb_data.uuid)
            except ValueError:
                logger.warning(
                    f"Skipping notebook with invalid uuid (length {len(nb_data.uuid)}) "
                    f"for user {current_user.id}"
                )
                skipped += 1
                continue

            page_uuids = []
            for raw_page in nb_data.pages:
                try:
                    page_uuids.append(parse_uuid(raw_page))
                except ValueError:
                    logger.warning(
                        f"Skipping page with invalid uuid (length {len(raw_page)}) "
                        f"for user {current_user.id}"
                    )
                    skipped += 1
            entries.append((nb_uuid, nb_data, page_uuids))

        counts = _apply_metadata_sync(db, current_user.id, entries)
        notebooks_created, notebooks_updated, pages_registered, pages_already_synced = counts

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
            skipped=skipped,
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
    current_user: User = Depends(get_clerk_session_user),
    db: Session = Depends(get_db),
):
    """
    Queue a sync to the specified target (or every enabled target for "all").

    Every OCR-completed page that has not been synced to the target yet, and
    is not already queued, gets a ``page_text`` row in the sync queue
    (optionally only pages of ``notebook_uuids``). The sync worker does the
    writing; this endpoint never calls the target. ``skipped_count`` counts
    pages already synced or queued. Only targets that accept page text are
    used.
    """
    try:
        if request.target_name == "all":
            configs = [
                config
                for config in db.query(IntegrationConfig)
                .filter(
                    IntegrationConfig.user_id == current_user.id,
                    IntegrationConfig.is_enabled == True,
                )
                .all()
                if supports(config.target_name, PAGE_TEXT)
            ]
        else:
            if not supports(request.target_name, PAGE_TEXT):
                raise HTTPException(
                    status_code=400,
                    detail=f"Integration '{request.target_name}' does not sync notebook pages",
                )
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

        for config in configs:
            if missing_config(config.target_name, config.get_config()):
                raise HTTPException(
                    status_code=400,
                    detail=f"Integration '{config.target_name}' is not fully configured. Please reconnect it.",
                )

        queued = 0
        skipped = 0
        for config in configs:
            stats = queue_pages_for_sync(
                db, current_user.id, config.target_name, request.notebook_uuids
            )
            queued += stats["queued_count"]
            skipped += stats["skipped_count"]

        return SyncResponse(
            success=True,
            message=f"Queued {queued} pages for {request.target_name}",
            synced_count=0,
            failed_count=0,
            skipped_count=skipped,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error triggering sync: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An internal error occurred")


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
        raise HTTPException(status_code=500, detail="An internal error occurred")


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
        raise HTTPException(status_code=500, detail="An internal error occurred")


# --- Deleted notebook endpoints (agent-facing) ---


class DeletedNotebookItem(BaseModel):
    notebook_uuid: str
    visible_name: str
    deleted_at: str


class DeletedNotebooksResponse(BaseModel):
    deleted_notebooks: list[DeletedNotebookItem]


class AcknowledgeRequest(BaseModel):
    action: Literal["resync", "dismiss"] = Field(..., description="'resync' or 'dismiss'")


@router.get("/deleted-notebooks", response_model=DeletedNotebooksResponse)
async def get_deleted_notebooks(
    current_user: User = Depends(get_clerk_active_user),
    db: Session = Depends(get_db),
):
    """Return notebooks deleted on the server that the agent hasn't acknowledged yet."""
    tombstones = (
        db.query(DeletedNotebook)
        .filter(DeletedNotebook.user_id == current_user.id)
        .all()
    )

    return DeletedNotebooksResponse(
        deleted_notebooks=[
            DeletedNotebookItem(
                notebook_uuid=t.notebook_uuid,
                visible_name=t.visible_name,
                deleted_at=t.deleted_at.isoformat(),
            )
            for t in tombstones
        ]
    )


@router.post("/deleted-notebooks/{notebook_uuid}/acknowledge")
async def acknowledge_deleted_notebook(
    notebook_uuid: str,
    body: AcknowledgeRequest,
    current_user: User = Depends(get_clerk_active_user),
    db: Session = Depends(get_db),
):
    """
    Acknowledge a deleted notebook tombstone.

    Actions:
    - 'resync': Agent will re-sync the notebook from scratch. Tombstone is removed.
    - 'dismiss': Agent will keep the notebook excluded. Tombstone is removed.
    """
    deleted = (
        db.query(DeletedNotebook)
        .filter(
            DeletedNotebook.user_id == current_user.id,
            DeletedNotebook.notebook_uuid == notebook_uuid,
        )
        .delete()
    )

    if not deleted:
        raise HTTPException(status_code=404, detail="Tombstone not found")

    db.commit()

    logger.info(
        f"User {current_user.id} acknowledged deleted notebook {notebook_uuid} "
        f"with action={body.action}"
    )

    return {"status": "ok", "action": body.action}
