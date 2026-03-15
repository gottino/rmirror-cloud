"""API endpoints for Obsidian sync integration."""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.clerk import get_clerk_active_user
from app.auth.dependencies import get_obsidian_user
from app.database import get_db
from app.models.notebook import Notebook
from app.models.notebook_page import NotebookPage
from app.models.page import OcrStatus, Page
from app.models.sync_record import IntegrationConfig, SyncRecord
from app.models.user import User
from app.services.obsidian_service import generate_api_key, hash_api_key

logger = logging.getLogger(__name__)
router = APIRouter(tags=["obsidian"])


# --- Pydantic Models ---


class ObsidianEnableResponse(BaseModel):
    api_key: str
    enabled: bool


class ObsidianStatusResponse(BaseModel):
    enabled: bool
    last_sync: Optional[str] = None
    total_notebooks_synced: int = 0
    total_pages_synced: int = 0
    pending_notebooks: int = 0


class SyncPageResponse(BaseModel):
    page_uuid: str
    page_number: int
    ocr_text: str


class SyncNotebookResponse(BaseModel):
    notebook_uuid: str
    visible_name: str
    folder_path: Optional[str]
    page_count: int
    content_hash: str
    last_modified: str
    pages: list[SyncPageResponse]


class SyncResponse(BaseModel):
    notebooks: list[SyncNotebookResponse]
    deleted_notebook_uuids: list[str]
    has_more: bool
    next_cursor: Optional[str] = None


class SyncConfirmNotebook(BaseModel):
    notebook_uuid: str
    content_hash: str
    file_path: str


class SyncConfirmRequest(BaseModel):
    synced_notebooks: list[SyncConfirmNotebook]
    deleted_notebooks: list[str] = []


class SyncConfirmResponse(BaseModel):
    status: str
    confirmed: int


# --- Helper Functions ---


def _enable_obsidian(user: User, db: Session) -> ObsidianEnableResponse:
    """Create Obsidian integration config with API key. Raises 400 if already exists."""
    existing = (
        db.query(IntegrationConfig)
        .filter(
            IntegrationConfig.user_id == user.id,
            IntegrationConfig.target_name == "obsidian",
        )
        .first()
    )

    if existing:
        raise HTTPException(
            status_code=400,
            detail="Obsidian integration already exists. Use regenerate-key to get a new key.",
        )

    raw_key = generate_api_key()
    config = IntegrationConfig(
        user_id=user.id,
        target_name="obsidian",
        is_enabled=True,
        api_key_hash=hash_api_key(raw_key),
    )
    config.set_config({"base_folder": "rMirror"})

    db.add(config)
    db.commit()
    db.refresh(config)

    logger.info(f"Enabled Obsidian integration for user {user.id}")
    return ObsidianEnableResponse(api_key=raw_key, enabled=True)


def _regenerate_key(user: User, db: Session) -> ObsidianEnableResponse:
    """Regenerate API key for existing Obsidian integration. Raises 404 if not found."""
    config = (
        db.query(IntegrationConfig)
        .filter(
            IntegrationConfig.user_id == user.id,
            IntegrationConfig.target_name == "obsidian",
        )
        .first()
    )

    if not config:
        raise HTTPException(
            status_code=404,
            detail="Obsidian integration not found. Enable it first.",
        )

    raw_key = generate_api_key()
    config.api_key_hash = hash_api_key(raw_key)
    db.commit()

    logger.info(f"Regenerated Obsidian API key for user {user.id}")
    return ObsidianEnableResponse(api_key=raw_key, enabled=config.is_enabled)


def _disable_obsidian(user: User, db: Session) -> dict:
    """Disable Obsidian integration and clear API key. Raises 404 if not found."""
    config = (
        db.query(IntegrationConfig)
        .filter(
            IntegrationConfig.user_id == user.id,
            IntegrationConfig.target_name == "obsidian",
        )
        .first()
    )

    if not config:
        raise HTTPException(
            status_code=404,
            detail="Obsidian integration not found.",
        )

    config.is_enabled = False
    config.api_key_hash = None
    db.commit()

    logger.info(f"Disabled Obsidian integration for user {user.id}")
    return {"success": True, "message": "Obsidian integration disabled"}


def _get_changed_notebooks(
    db: Session,
    user_id: int,
    limit: int = 50,
    cursor: Optional[str] = None,
) -> tuple[list[Notebook], list[str], bool, Optional[str]]:
    """
    Detect notebooks with changed content for Obsidian sync.

    Returns:
        (changed_notebooks, deleted_uuids, has_more, next_cursor)
    """
    # Query notebooks with content hash, not deleted, ordered by id
    query = (
        db.query(Notebook)
        .filter(
            Notebook.user_id == user_id,
            Notebook.obsidian_content_hash.isnot(None),
            Notebook.deleted == False,  # noqa: E712
        )
        .order_by(Notebook.id)
    )

    if cursor:
        try:
            cursor_id = int(cursor)
            query = query.filter(Notebook.id > cursor_id)
        except (ValueError, TypeError):
            pass

    # Fetch limit+1 to detect has_more
    notebooks = query.limit(limit + 1).all()

    has_more = len(notebooks) > limit
    if has_more:
        notebooks = notebooks[:limit]

    next_cursor = str(notebooks[-1].id) if has_more and notebooks else None

    # Load existing sync records for obsidian
    notebook_uuids = [nb.notebook_uuid for nb in notebooks]
    sync_records = (
        db.query(SyncRecord)
        .filter(
            SyncRecord.user_id == user_id,
            SyncRecord.target_name == "obsidian",
            SyncRecord.item_type == "notebook",
            SyncRecord.status == "success",
            SyncRecord.page_uuid.in_(notebook_uuids) if notebook_uuids else False,
        )
        .all()
    )

    # Build hash lookup: notebook_uuid -> synced content_hash
    synced_hashes = {sr.page_uuid: sr.content_hash for sr in sync_records}

    # Filter to changed notebooks
    changed = [
        nb
        for nb in notebooks
        if nb.notebook_uuid not in synced_hashes
        or synced_hashes[nb.notebook_uuid] != nb.obsidian_content_hash
    ]

    # Find deleted notebooks that have sync records
    deleted_records = (
        db.query(SyncRecord)
        .join(Notebook, SyncRecord.page_uuid == Notebook.notebook_uuid)
        .filter(
            SyncRecord.user_id == user_id,
            SyncRecord.target_name == "obsidian",
            SyncRecord.item_type == "notebook",
            SyncRecord.status == "success",
            Notebook.deleted == True,  # noqa: E712
        )
        .all()
    )
    deleted_uuids = list({sr.page_uuid for sr in deleted_records if sr.page_uuid})

    return changed, deleted_uuids, has_more, next_cursor


# --- Management Endpoints (Clerk auth) ---


@router.post("/obsidian/enable", response_model=ObsidianEnableResponse)
async def enable_obsidian(
    current_user: User = Depends(get_clerk_active_user),
    db: Session = Depends(get_db),
):
    """Enable Obsidian integration and return API key."""
    return _enable_obsidian(current_user, db)


@router.post("/obsidian/regenerate-key", response_model=ObsidianEnableResponse)
async def regenerate_obsidian_key(
    current_user: User = Depends(get_clerk_active_user),
    db: Session = Depends(get_db),
):
    """Regenerate Obsidian API key."""
    return _regenerate_key(current_user, db)


@router.post("/obsidian/disable")
async def disable_obsidian(
    current_user: User = Depends(get_clerk_active_user),
    db: Session = Depends(get_db),
):
    """Disable Obsidian integration."""
    return _disable_obsidian(current_user, db)


@router.get("/obsidian/status", response_model=ObsidianStatusResponse)
async def obsidian_status(
    current_user: User = Depends(get_clerk_active_user),
    db: Session = Depends(get_db),
):
    """Get Obsidian integration status and sync stats."""
    config = (
        db.query(IntegrationConfig)
        .filter(
            IntegrationConfig.user_id == current_user.id,
            IntegrationConfig.target_name == "obsidian",
        )
        .first()
    )

    if not config:
        return ObsidianStatusResponse(enabled=False)

    # Count synced notebooks
    notebooks_synced = (
        db.query(SyncRecord)
        .filter(
            SyncRecord.user_id == current_user.id,
            SyncRecord.target_name == "obsidian",
            SyncRecord.item_type == "notebook",
            SyncRecord.status == "success",
        )
        .count()
    )

    # Count total pages across synced notebooks
    synced_notebook_uuids = [
        sr.page_uuid
        for sr in db.query(SyncRecord.page_uuid)
        .filter(
            SyncRecord.user_id == current_user.id,
            SyncRecord.target_name == "obsidian",
            SyncRecord.item_type == "notebook",
            SyncRecord.status == "success",
        )
        .all()
    ]

    pages_synced = 0
    if synced_notebook_uuids:
        pages_synced = (
            db.query(Page)
            .join(NotebookPage, NotebookPage.page_id == Page.id)
            .join(Notebook, NotebookPage.notebook_id == Notebook.id)
            .filter(
                Notebook.notebook_uuid.in_(synced_notebook_uuids),
                Page.ocr_status == OcrStatus.COMPLETED.value,
            )
            .count()
        )

    # Count pending notebooks (have content hash but no sync record or hash differs)
    total_with_hash = (
        db.query(Notebook)
        .filter(
            Notebook.user_id == current_user.id,
            Notebook.obsidian_content_hash.isnot(None),
            Notebook.deleted == False,  # noqa: E712
        )
        .count()
    )
    pending = max(0, total_with_hash - notebooks_synced)

    return ObsidianStatusResponse(
        enabled=config.is_enabled,
        last_sync=config.last_synced_at.isoformat() if config.last_synced_at else None,
        total_notebooks_synced=notebooks_synced,
        total_pages_synced=pages_synced,
        pending_notebooks=pending,
    )


# --- Sync Endpoints (API key auth) ---


@router.get("/obsidian/sync", response_model=SyncResponse)
async def sync_notebooks(
    current_user: User = Depends(get_obsidian_user),
    db: Session = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=200),
    cursor: Optional[str] = Query(default=None),
):
    """Get changed notebooks for Obsidian sync."""
    changed, deleted_uuids, has_more, next_cursor = _get_changed_notebooks(
        db, current_user.id, limit, cursor
    )

    notebook_responses = []
    for nb in changed:
        # Load pages via NotebookPage JOIN Page where OCR completed
        page_rows = (
            db.query(NotebookPage, Page)
            .join(Page, NotebookPage.page_id == Page.id)
            .filter(
                NotebookPage.notebook_id == nb.id,
                Page.ocr_status == OcrStatus.COMPLETED.value,
            )
            .order_by(NotebookPage.page_number)
            .all()
        )

        pages = [
            SyncPageResponse(
                page_uuid=page.page_uuid or "",
                page_number=np.page_number,
                ocr_text=page.ocr_text or "",
            )
            for np, page in page_rows
        ]

        notebook_responses.append(
            SyncNotebookResponse(
                notebook_uuid=nb.notebook_uuid,
                visible_name=nb.visible_name,
                folder_path=nb.full_path,
                page_count=len(pages),
                content_hash=nb.obsidian_content_hash or "",
                last_modified=nb.updated_at.isoformat(),
                pages=pages,
            )
        )

    # Update last_synced_at if there was data
    if notebook_responses or deleted_uuids:
        config = (
            db.query(IntegrationConfig)
            .filter(
                IntegrationConfig.user_id == current_user.id,
                IntegrationConfig.target_name == "obsidian",
            )
            .first()
        )
        if config:
            config.last_synced_at = datetime.utcnow()
            db.commit()

    return SyncResponse(
        notebooks=notebook_responses,
        deleted_notebook_uuids=deleted_uuids,
        has_more=has_more,
        next_cursor=next_cursor,
    )


@router.post("/obsidian/sync/confirm", response_model=SyncConfirmResponse)
async def confirm_sync(
    request: SyncConfirmRequest,
    current_user: User = Depends(get_obsidian_user),
    db: Session = Depends(get_db),
):
    """Confirm that notebooks have been synced to Obsidian vault."""
    confirmed = 0

    for item in request.synced_notebooks:
        # Upsert sync record
        existing = (
            db.query(SyncRecord)
            .filter(
                SyncRecord.user_id == current_user.id,
                SyncRecord.target_name == "obsidian",
                SyncRecord.page_uuid == item.notebook_uuid,
            )
            .first()
        )

        if existing:
            existing.content_hash = item.content_hash
            existing.external_id = item.file_path
            existing.status = "success"
            existing.synced_at = datetime.utcnow()
            existing.updated_at = datetime.utcnow()
        else:
            record = SyncRecord(
                user_id=current_user.id,
                target_name="obsidian",
                item_type="notebook",
                page_uuid=item.notebook_uuid,
                notebook_uuid=item.notebook_uuid,
                content_hash=item.content_hash,
                external_id=item.file_path,
                status="success",
                synced_at=datetime.utcnow(),
            )
            db.add(record)

        confirmed += 1

    # Delete sync records for deleted notebooks
    for notebook_uuid in request.deleted_notebooks:
        db.query(SyncRecord).filter(
            SyncRecord.user_id == current_user.id,
            SyncRecord.target_name == "obsidian",
            SyncRecord.page_uuid == notebook_uuid,
        ).delete()

    db.commit()

    return SyncConfirmResponse(status="ok", confirmed=confirmed)
