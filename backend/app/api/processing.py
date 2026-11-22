"""Processing endpoints for notebook OCR and handwriting extraction."""

import asyncio
import json
import logging
import os
import tempfile
import uuid
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from app.auth.clerk import get_clerk_active_user, get_clerk_session_user
from app.config import get_settings
from app.core.notebook_metadata_service import NotebookMetadataService
from app.core.ocr_service import OCRService
from app.core.rm_converter import RMConverter
from app.core.rm_metadata import RMMetadataParser
from app.core.upserts import get_or_create_notebook, get_or_create_page
from app.database import get_db
from app.dependencies import get_storage_service
from app.middleware.rate_limit import UPLOAD_LIMIT, limiter
from app.models.notebook import DocumentType, Notebook
from app.models.page import OcrStatus, Page
from app.models.user import User
from app.services import quota_service
from app.services.page_events import on_ocr_completed, update_obsidian_content_hash
from app.services.sync_queue import queue_notebook_metadata_sync
from app.storage import StorageService
from app.utils.files import (
    calculate_file_hash,
    parse_uuid,
    read_upload_limited,
    require_uuid,
)
from app.utils.umami import track_event

logger = logging.getLogger(__name__)
router = APIRouter(tags=["processing"])


class ProcessRMFileResponse(BaseModel):
    """Response for .rm file processing."""

    success: bool
    extracted_text: str
    page_count: int
    metadata: dict | None = None
    notebook_id: int | None = None
    page_id: int | None = None


@router.post("/rm-file", response_model=ProcessRMFileResponse)
# Per user (settings.rate_limit_upload, default 120/minute): sized for an
# initial sync, where the agent uploads every page back to back.
@limiter.limit(UPLOAD_LIMIT)
async def process_rm_file(
    request: Request,
    rm_file: UploadFile = File(..., description=".rm file from reMarkable tablet"),
    metadata_file: UploadFile | None = File(None, description="Optional .metadata file"),
    current_user: User = Depends(get_clerk_active_user),
    db: Session = Depends(get_db),
    storage: StorageService = Depends(get_storage_service),
):
    """
    Process a reMarkable .rm file: convert to PDF, extract text, and save to database.

    This endpoint:
    1. Accepts a .rm file (and optional .metadata file)
    2. Converts .rm → SVG → PDF
    3. Sends PDF to Claude Vision for OCR
    4. Creates/updates Notebook and Page records in database
    5. Stores .rm file in storage
    6. Returns extracted text with database IDs

    Args:
        rm_file: The .rm file to process
        metadata_file: Optional .metadata JSON file for notebook metadata
        current_user: Authenticated user
        db: Database session
        storage: Storage service

    Returns:
        ProcessRMFileResponse with extracted text, metadata, and database IDs
    """
    # Validate file type
    if not rm_file.filename or not rm_file.filename.endswith(".rm"):
        raise HTTPException(
            status_code=400,
            detail="Invalid file type. Expected .rm file from reMarkable tablet.",
        )

    # The stem becomes the page UUID and part of storage keys: it must be a UUID.
    page_uuid = require_uuid(rm_file.filename.removesuffix(".rm"), "page filename")

    # Same for the notebook UUID taken from the .metadata filename.
    notebook_uuid = None
    if (
        metadata_file
        and metadata_file.filename
        and metadata_file.filename.endswith(".metadata")
    ):
        notebook_uuid = require_uuid(
            metadata_file.filename.removesuffix(".metadata"), "metadata filename"
        )

    logger.info(f"Processing .rm file: {page_uuid} for user {current_user.id}")

    # Read the uploads with size limits (413 if exceeded) before any work is done
    rm_content = await read_upload_limited(
        rm_file, get_settings().max_rm_file_size, ".rm file"
    )
    metadata_bytes = None
    if metadata_file:
        metadata_bytes = await read_upload_limited(
            metadata_file, get_settings().max_metadata_file_size, ".metadata file"
        )

    temp_rm_path = None
    try:

        # Calculate file hash
        file_stream = BytesIO(rm_content)
        file_hash = calculate_file_hash(file_stream)

        # Parse metadata if provided
        metadata_obj = None
        metadata_dict = None
        visible_name = None

        if metadata_file:
            try:
                metadata_content = metadata_bytes
                parser = RMMetadataParser()
                metadata_obj = parser.parse_bytes(metadata_content)
                metadata_dict = {
                    "visible_name": metadata_obj.visible_name,
                    "document_type": metadata_obj.document_type,
                    "parent": metadata_obj.parent,
                    "last_modified": metadata_obj.last_modified.isoformat(),
                    "version": metadata_obj.version,
                    "pinned": metadata_obj.pinned,
                }
                visible_name = metadata_obj.visible_name
                logger.info(f"Parsed metadata: {metadata_obj.visible_name}")
            except Exception as e:
                logger.warning(f"Failed to parse metadata file: {e}")

        # Generate notebook UUID if not provided via metadata
        if not notebook_uuid:
            notebook_uuid = str(uuid.uuid4())
            logger.info(f"Generated new notebook UUID: {notebook_uuid}")

        # Use visible name from metadata or default
        if not visible_name:
            visible_name = f"Notebook {notebook_uuid[:8]}"

        # Find or create Notebook record (insert-or-ignore, safe under concurrency)
        notebook, notebook_created = get_or_create_notebook(
            db,
            current_user.id,
            notebook_uuid,
            visible_name=visible_name,
            document_type=DocumentType.NOTEBOOK,
            metadata_json=json.dumps(metadata_dict) if metadata_dict else None,
            last_synced_at=datetime.utcnow(),
        )

        if notebook_created:
            db.commit()
            db.refresh(notebook)
            logger.info(f"Created notebook {visible_name} ({notebook_uuid}) with ID: {notebook.id}")

            # Track first notebook milestone
            if not current_user.first_notebook_synced_at:
                current_user.first_notebook_synced_at = datetime.utcnow()
                db.commit()
                await track_event("first_sync_completed", user_id=current_user.id)
        else:
            logger.info(f"Found existing notebook: {notebook.id}")
            # Update last_synced_at when syncing existing notebook
            notebook.last_synced_at = datetime.utcnow()

        # Save .rm file to temporary location for processing
        # (the path is generated by tempfile, never derived from the client)
        fd, tmp_name = tempfile.mkstemp(suffix=".rm")
        temp_rm_path = Path(tmp_name)
        with os.fdopen(fd, "wb") as tmp_file:
            tmp_file.write(rm_content)

        # Initialize services
        converter = RMConverter()
        ocr_service = OCRService()

        # Check if file has content
        if not await asyncio.to_thread(converter.has_content, temp_rm_path):
            logger.warning(f"File {rm_file.filename} has no content")
            temp_rm_path.unlink(missing_ok=True)
            return ProcessRMFileResponse(
                success=True,
                extracted_text="",
                page_count=0,
                metadata=metadata_dict,
                notebook_id=notebook.id,
                page_id=None,
            )

        # Find or create Page record (before expensive OCR operations)
        page = db.query(Page).filter(
            Page.notebook_id == notebook.id,
            Page.page_uuid == page_uuid
        ).first()

        # Check if we need to process this file (new file, file hash changed, or stub from metadata sync)
        needs_processing = (
            page is None or
            page.file_hash != file_hash or
            page.ocr_status == OcrStatus.FAILED or
            page.ocr_status == OcrStatus.NOT_SYNCED  # Page stub from metadata sync
        )
        # An unchanged COMPLETED page is not re-OCR'd even when its text is
        # empty: a page with no handwriting legitimately OCRs to "".

        extracted_text = ""
        pdf_bytes = None
        ocr_status = OcrStatus.PENDING

        if needs_processing:
            # Convert .rm to PDF (always, regardless of quota)
            logger.info(f"Converting {rm_file.filename} to PDF (file hash changed or new file)")
            pdf_bytes = await asyncio.to_thread(converter.rm_to_pdf_bytes, temp_rm_path)

            # Reserve quota BEFORE OCR (not before upload). The reservation is a
            # single conditional UPDATE, so concurrent uploads can't overspend.
            try:
                has_quota = quota_service.reserve_quota(db, current_user.id)
            except quota_service.NoSubscriptionError:
                # Should not happen (the Clerk webhook creates a subscription
                # with the user), but treat it as "no quota" rather than a 500.
                logger.error(
                    f"User {current_user.id} has no subscription; storing page "
                    f"without OCR (PENDING_QUOTA)"
                )
                has_quota = False
                quota_status = None
            else:
                quota_status = (
                    None if has_quota else quota_service.get_quota_status(db, current_user.id)
                )

            if has_quota:
                # Quota reserved - run OCR, giving the unit back if OCR fails
                logger.info(f"Extracting text from {rm_file.filename} via OCR")
                try:
                    extracted_text = await ocr_service.extract_text_from_pdf(pdf_bytes)
                except Exception:
                    quota_service.release_quota(db, current_user.id)
                    raise
                if extracted_text:
                    logger.info(f"Consumed 1 OCR quota unit for user {current_user.id}")
                else:
                    # A blank page is a legitimate result; don't charge for it.
                    quota_service.release_quota(db, current_user.id)
                    logger.info(f"OCR found no text in {rm_file.filename}; quota not charged")
                ocr_status = OcrStatus.COMPLETED
            else:
                # Quota exhausted - skip OCR but keep page

                # Hard cap: Limit pending pages to prevent abuse
                pending_count = db.query(Page).filter(
                    Page.notebook_id.in_(
                        db.query(Notebook.id).filter(Notebook.user_id == current_user.id)
                    ),
                    Page.ocr_status == OcrStatus.PENDING_QUOTA
                ).count()

                if pending_count >= 100:
                    raise HTTPException(
                        status_code=429,  # Too Many Requests
                        detail={
                            "error": "pending_quota_limit",
                            "message": "You have 100 pages pending OCR. Please upgrade to Pro or wait for your quota to reset.",
                            "pending_count": pending_count,
                            "quota": quota_status,
                        }
                    )

                if quota_status is not None:
                    await track_event(
                        "quota_exceeded",
                        {"used": quota_status["used"], "limit": quota_status["limit"]},
                        user_id=current_user.id,
                    )
                    logger.info(
                        f"Quota exhausted ({quota_status['used']}/{quota_status['limit']}) - "
                        f"page uploaded without OCR (will be processed when quota resets)"
                    )
                ocr_status = OcrStatus.PENDING_QUOTA
                extracted_text = ""
        else:
            logger.info(f"Skipping OCR for {rm_file.filename} - file unchanged (hash: {file_hash})")
            # File unchanged - reuse existing OCR text and PDF
            extracted_text = page.ocr_text or ""
            # Still need to convert to PDF for storage if it doesn't exist
            if not page.pdf_s3_key:
                logger.info(f"Converting {rm_file.filename} to PDF (missing PDF)")
                pdf_bytes = await asyncio.to_thread(converter.rm_to_pdf_bytes, temp_rm_path)

        # Store .rm file in storage
        storage_key = f"users/{current_user.id}/notebooks/{notebook_uuid}/pages/{page_uuid}.rm"
        file_stream.seek(0)
        await storage.upload_file(
            file_stream,
            storage_key,
            content_type="application/octet-stream"
        )
        logger.info(f"Stored .rm file at: {storage_key}")

        # Store page PDF (if we generated one)
        pdf_storage_key = f"users/{current_user.id}/notebooks/{notebook_uuid}/pages/{page_uuid}.pdf"
        if pdf_bytes:
            pdf_stream = BytesIO(pdf_bytes)
            await storage.upload_file(
                pdf_stream,
                pdf_storage_key,
                content_type="application/pdf"
            )
            logger.info(f"Stored page PDF at: {pdf_storage_key}")

        # Create or update Page record
        page_created = False
        if not page:
            # Create new page (page_number is managed in notebook_pages mapping table).
            # A concurrent upload of the same page may have inserted it meanwhile;
            # then the existing row is updated below instead.
            page, page_created = get_or_create_page(
                db,
                notebook.id,
                page_uuid,
                s3_key=storage_key,
                pdf_s3_key=pdf_storage_key,
                file_hash=file_hash,
                ocr_status=ocr_status,
                ocr_text=extracted_text,
                ocr_completed_at=datetime.utcnow() if ocr_status == OcrStatus.COMPLETED else None,
            )
        if not page_created:
            # Update existing page
            page.s3_key = storage_key
            if pdf_bytes:
                page.pdf_s3_key = pdf_storage_key
            page.file_hash = file_hash

            # Only update OCR results if we actually processed the file
            if needs_processing:
                page.ocr_text = extracted_text
                page.ocr_status = ocr_status
                page.ocr_completed_at = datetime.utcnow() if ocr_status == OcrStatus.COMPLETED else None

        db.commit()
        db.refresh(page)

        if ocr_status == OcrStatus.COMPLETED:
            # OCR ran in this request: Obsidian hash + integration syncs. Syncs
            # depend on OCR having produced text, not on quota left afterwards.
            on_ocr_completed(db, page, notebook)
        else:
            # Page may have left COMPLETED (e.g. new content stored as
            # PENDING_QUOTA), so keep the Obsidian content hash current.
            update_obsidian_content_hash(db, notebook)

        # Track first OCR milestone
        if ocr_status == OcrStatus.COMPLETED and not current_user.first_ocr_completed_at:
            current_user.first_ocr_completed_at = datetime.utcnow()
            db.commit()
            await track_event("ocr_completed", {"is_first": True}, user_id=current_user.id)

        # Mark the combined notebook PDF as needing a rebuild instead of rebuilding
        # it inline. Rebuilding on every page upload re-downloaded and re-stitched
        # every page (O(N^2) S3 round-trips for an N-page sync). The background
        # worker debounces this and rebuilds once the notebook goes quiet. See
        # app/services/notebook_pdf.py.
        if pdf_bytes:  # only a new page PDF changes the combined PDF
            notebook.pdf_dirty_at = datetime.utcnow()
            db.commit()

        # Clean up temp file
        temp_rm_path.unlink(missing_ok=True)

        logger.info(
            f"Successfully processed {rm_file.filename}: "
            f"notebook_id={notebook.id}, page_id={page.id}, "
            f"extracted {len(extracted_text)} characters"
        )

        return ProcessRMFileResponse(
            success=True,
            extracted_text=extracted_text,
            page_count=1,  # .rm files are single pages
            metadata=metadata_dict,
            notebook_id=notebook.id,
            page_id=page.id,
        )

    except HTTPException:
        # Re-raise HTTPExceptions (e.g., 402, 429) without wrapping
        if temp_rm_path and temp_rm_path.exists():
            temp_rm_path.unlink(missing_ok=True)
        raise
    except Exception as e:
        logger.error(f"Failed to process .rm file: {e}", exc_info=True)
        # Clean up temp file on error
        if temp_rm_path and temp_rm_path.exists():
            temp_rm_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to process .rm file: {str(e)}"
        )


class UpdateMetadataRequest(BaseModel):
    """Request to update notebook metadata."""

    notebook_uuid: str
    visible_name: str
    parent_uuid: Optional[str] = None
    document_type: str = "notebook"

    @field_validator("notebook_uuid")
    @classmethod
    def _validate_notebook_uuid(cls, v: str) -> str:
        return parse_uuid(v)

    pinned: Optional[bool] = None
    deleted: Optional[bool] = None
    version: Optional[int] = None
    last_modified: Optional[str] = None
    last_opened: Optional[str] = None
    last_opened_page: Optional[int] = None
    authors: Optional[str] = None
    publisher: Optional[str] = None
    publication_date: Optional[str] = None


class UpdateMetadataResponse(BaseModel):
    """Response for metadata update."""

    success: bool
    notebook_id: int
    notebook_uuid: str
    full_path: str
    message: str


@router.post("/metadata/update", response_model=UpdateMetadataResponse)
async def update_notebook_metadata(
    request: UpdateMetadataRequest,
    current_user: User = Depends(get_clerk_active_user),
    db: Session = Depends(get_db),
):
    """
    Update or create notebook metadata and rebuild folder paths.

    This endpoint allows clients to sync metadata from reMarkable devices,
    including folder hierarchies, document types, and reMarkable-specific
    state like pinned, deleted, etc.

    After updating the metadata, it automatically rebuilds the full folder
    path for the notebook and any affected children.

    Args:
        request: Metadata update request
        current_user: Authenticated user
        db: Database session

    Returns:
        UpdateMetadataResponse with updated notebook info
    """
    try:
        # Initialize metadata service
        metadata_service = NotebookMetadataService(db, current_user.id)

        # Prepare metadata dict
        metadata = {}
        if request.pinned is not None:
            metadata["pinned"] = request.pinned
        if request.deleted is not None:
            metadata["deleted"] = request.deleted
        if request.version is not None:
            metadata["version"] = request.version
        if request.last_modified:
            metadata["last_modified"] = request.last_modified
        if request.last_opened:
            metadata["last_opened"] = request.last_opened
        if request.last_opened_page is not None:
            metadata["last_opened_page"] = request.last_opened_page
        if request.authors:
            metadata["authors"] = request.authors
        if request.publisher:
            metadata["publisher"] = request.publisher
        if request.publication_date:
            metadata["publication_date"] = request.publication_date

        # Update notebook
        notebook = metadata_service.update_single_notebook_metadata(
            notebook_uuid=request.notebook_uuid,
            visible_name=request.visible_name,
            parent_uuid=request.parent_uuid,
            document_type=request.document_type,
            metadata=metadata if metadata else None,
        )

        # If this is a folder, update paths for all children
        if request.document_type == "folder":
            metadata_service.update_paths_for_subtree(request.notebook_uuid)

        # Queue a lightweight, properties-only update for the integrations that
        # accept one (target registry). The sync worker writes it; this request
        # never calls an integration itself.
        if request.document_type == "notebook":
            try:
                # Integrations are blocked while the OCR quota is exhausted.
                quota_status = quota_service.get_quota_status(db, current_user.id)

                if quota_status["is_exhausted"]:
                    logger.warning(
                        f"Skipping integration sync for user {current_user.id} - quota exhausted. "
                        "Metadata updates will not be synced to integrations."
                    )
                else:
                    queued = queue_notebook_metadata_sync(db, notebook)
                    logger.info(
                        f"Queued metadata sync for notebook {notebook.notebook_uuid} "
                        f"to {len(queued)} integrations"
                    )
            except Exception as e:
                db.rollback()
                logger.warning(f"Failed to queue metadata sync: {e}")
                # Don't fail the whole request if sync queueing fails

        return UpdateMetadataResponse(
            success=True,
            notebook_id=notebook.id,
            notebook_uuid=notebook.notebook_uuid,
            full_path=notebook.full_path or "",
            message=f"Updated metadata for {notebook.visible_name}",
        )

    except Exception as e:
        logger.error(f"Failed to update metadata: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update metadata: {str(e)}"
        )


@router.post("/metadata/rebuild-paths")
async def rebuild_all_paths(
    current_user: User = Depends(get_clerk_session_user),
    db: Session = Depends(get_db),
):
    """
    Rebuild all notebook paths for the current user.

    Useful after bulk metadata updates or to fix any path inconsistencies.

    Args:
        current_user: Authenticated user
        db: Database session

    Returns:
        Dict with number of updated paths
    """
    try:
        metadata_service = NotebookMetadataService(db, current_user.id)
        updated_count = metadata_service.update_notebook_paths()

        return {
            "success": True,
            "updated_count": updated_count,
            "message": f"Rebuilt paths for {updated_count} notebooks",
        }

    except Exception as e:
        logger.error(f"Failed to rebuild paths: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to rebuild paths: {str(e)}"
        )
