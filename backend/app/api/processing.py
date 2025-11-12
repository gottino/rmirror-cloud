"""Processing endpoints for notebook OCR and handwriting extraction."""

import json
import logging
import uuid
from datetime import datetime
from io import BytesIO
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_active_user
from app.core.ocr_service import OCRService
from app.core.pdf_service import PDFService
from app.core.rm_converter import RMConverter
from app.core.rm_metadata import RMMetadataParser
from app.database import get_db
from app.dependencies import get_storage_service
from app.models.notebook import Notebook, DocumentType
from app.models.page import Page, OcrStatus
from app.models.user import User
from app.storage import StorageService
from app.utils.files import calculate_file_hash

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


class ProcessRMFileRequest(BaseModel):
    """Request to process an uploaded .rm file."""

    notebook_id: str | None = None  # Optional: link to existing notebook


@router.post("/rm-file", response_model=ProcessRMFileResponse)
async def process_rm_file(
    rm_file: UploadFile = File(..., description=".rm file from reMarkable tablet"),
    metadata_file: UploadFile | None = File(None, description="Optional .metadata file"),
    current_user: User = Depends(get_current_active_user),
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

    logger.info(f"Processing .rm file: {rm_file.filename} for user {current_user.id}")

    temp_rm_path = None
    try:
        # Read .rm file content
        rm_content = await rm_file.read()
        file_size = len(rm_content)

        # Calculate file hash
        file_stream = BytesIO(rm_content)
        file_hash = calculate_file_hash(file_stream)

        # Parse metadata if provided
        metadata_obj = None
        metadata_dict = None
        notebook_uuid = None
        visible_name = None

        if metadata_file:
            try:
                # Extract notebook UUID from metadata filename (format: UUID.metadata)
                if metadata_file.filename and metadata_file.filename.endswith(".metadata"):
                    notebook_uuid = metadata_file.filename.rstrip(".metadata")
                    logger.info(f"Extracted notebook UUID from metadata filename: {notebook_uuid}")

                metadata_content = await metadata_file.read()
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

        # Extract page UUID from .rm filename
        page_uuid = rm_file.filename.rstrip(".rm")

        # Generate notebook UUID if not provided via metadata
        if not notebook_uuid:
            notebook_uuid = str(uuid.uuid4())
            logger.info(f"Generated new notebook UUID: {notebook_uuid}")

        # Use visible name from metadata or default
        if not visible_name:
            visible_name = f"Notebook {notebook_uuid[:8]}"

        # Find or create Notebook record
        notebook = db.query(Notebook).filter(
            Notebook.user_id == current_user.id,
            Notebook.notebook_uuid == notebook_uuid
        ).first()

        if not notebook:
            logger.info(f"Creating new notebook: {visible_name} ({notebook_uuid})")
            notebook = Notebook(
                user_id=current_user.id,
                notebook_uuid=notebook_uuid,
                visible_name=visible_name,
                document_type=DocumentType.NOTEBOOK,
                metadata_json=json.dumps(metadata_dict) if metadata_dict else None,
                last_synced_at=datetime.utcnow(),
            )
            db.add(notebook)
            db.commit()
            db.refresh(notebook)
            logger.info(f"Created notebook with ID: {notebook.id}")
        else:
            logger.info(f"Found existing notebook: {notebook.id}")

        # Save .rm file to temporary location for processing
        temp_rm_path = Path(f"/tmp/{rm_file.filename}")
        temp_rm_path.parent.mkdir(parents=True, exist_ok=True)
        temp_rm_path.write_bytes(rm_content)

        # Initialize services
        converter = RMConverter()
        ocr_service = OCRService()

        # Check if file has content
        if not converter.has_content(temp_rm_path):
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

        # Convert .rm to PDF
        logger.info(f"Converting {rm_file.filename} to PDF")
        pdf_bytes = converter.rm_to_pdf_bytes(temp_rm_path)

        # Extract text via Claude Vision OCR
        logger.info(f"Extracting text from {rm_file.filename} via OCR")
        extracted_text = await ocr_service.extract_text_from_pdf(pdf_bytes)

        # Store .rm file in storage
        storage_key = f"users/{current_user.id}/notebooks/{notebook_uuid}/pages/{page_uuid}.rm"
        file_stream.seek(0)
        await storage.upload_file(
            file_stream,
            storage_key,
            content_type="application/octet-stream"
        )
        logger.info(f"Stored .rm file at: {storage_key}")

        # Store page PDF
        pdf_storage_key = f"users/{current_user.id}/notebooks/{notebook_uuid}/pages/{page_uuid}.pdf"
        pdf_stream = BytesIO(pdf_bytes)
        await storage.upload_file(
            pdf_stream,
            pdf_storage_key,
            content_type="application/pdf"
        )
        logger.info(f"Stored page PDF at: {pdf_storage_key}")

        # Find or create Page record
        page = db.query(Page).filter(
            Page.notebook_id == notebook.id,
            Page.page_uuid == page_uuid
        ).first()

        if not page:
            # Count existing pages to determine page number
            page_count = db.query(Page).filter(Page.notebook_id == notebook.id).count()
            page = Page(
                notebook_id=notebook.id,
                page_number=page_count + 1,
                page_uuid=page_uuid,
                s3_key=storage_key,
                pdf_s3_key=pdf_storage_key,
                file_hash=file_hash,
                ocr_status=OcrStatus.PROCESSING,
            )
            db.add(page)
        else:
            # Update existing page
            page.s3_key = storage_key
            page.pdf_s3_key = pdf_storage_key
            page.file_hash = file_hash
            page.ocr_status = OcrStatus.PROCESSING

        # Save OCR results
        page.ocr_text = extracted_text
        page.ocr_status = OcrStatus.COMPLETED
        page.ocr_completed_at = datetime.utcnow()

        db.commit()
        db.refresh(page)

        # Regenerate combined notebook PDF
        logger.info(f"Regenerating combined PDF for notebook {notebook.id}")
        try:
            # Get all pages for this notebook, sorted by page number
            all_pages = db.query(Page).filter(
                Page.notebook_id == notebook.id,
                Page.pdf_s3_key.isnot(None)
            ).order_by(Page.page_number).all()

            if all_pages:
                # Download all page PDFs
                page_pdfs = []
                for p in all_pages:
                    page_pdf_bytes = await storage.download_file(p.pdf_s3_key)
                    page_pdfs.append(page_pdf_bytes)

                # Combine into notebook PDF
                pdf_service = PDFService()
                combined_pdf = pdf_service.combine_page_pdfs(page_pdfs)

                # Store combined notebook PDF
                notebook_pdf_key = f"users/{current_user.id}/notebooks/{notebook_uuid}/notebook.pdf"
                combined_pdf_stream = BytesIO(combined_pdf)
                await storage.upload_file(
                    combined_pdf_stream,
                    notebook_pdf_key,
                    content_type="application/pdf"
                )

                # Update notebook with PDF location
                notebook.notebook_pdf_s3_key = notebook_pdf_key
                db.commit()

                logger.info(f"Combined {len(all_pages)} pages into notebook PDF at: {notebook_pdf_key}")
        except Exception as e:
            logger.error(f"Failed to generate notebook PDF: {e}", exc_info=True)
            # Don't fail the whole request if PDF generation fails

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

    except Exception as e:
        logger.error(f"Failed to process .rm file: {e}", exc_info=True)
        # Clean up temp file on error
        if temp_rm_path and temp_rm_path.exists():
            temp_rm_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to process .rm file: {str(e)}"
        )
