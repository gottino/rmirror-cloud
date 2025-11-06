"""Processing endpoints for notebook OCR and handwriting extraction."""

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_active_user
from app.core.ocr_service import OCRService
from app.core.rm_converter import RMConverter
from app.core.rm_metadata import RMMetadataParser
from app.database import get_db
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/processing", tags=["processing"])


class ProcessRMFileResponse(BaseModel):
    """Response for .rm file processing."""

    success: bool
    extracted_text: str
    page_count: int
    metadata: dict | None = None


class ProcessRMFileRequest(BaseModel):
    """Request to process an uploaded .rm file."""

    notebook_id: str | None = None  # Optional: link to existing notebook


@router.post("/rm-file", response_model=ProcessRMFileResponse)
async def process_rm_file(
    rm_file: UploadFile = File(..., description=".rm file from reMarkable tablet"),
    metadata_file: UploadFile | None = File(None, description="Optional .metadata file"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Process a reMarkable .rm file: convert to PDF and extract handwritten text via OCR.

    This endpoint:
    1. Accepts a .rm file (and optional .metadata file)
    2. Converts .rm → SVG → PDF
    3. Sends PDF to Claude Vision for OCR
    4. Returns extracted text

    Args:
        rm_file: The .rm file to process
        metadata_file: Optional .metadata JSON file for notebook metadata
        current_user: Authenticated user
        db: Database session

    Returns:
        ProcessRMFileResponse with extracted text and metadata
    """
    # Validate file type
    if not rm_file.filename or not rm_file.filename.endswith(".rm"):
        raise HTTPException(
            status_code=400,
            detail="Invalid file type. Expected .rm file from reMarkable tablet.",
        )

    logger.info(f"Processing .rm file: {rm_file.filename} for user {current_user.id}")

    try:
        # Save .rm file to temporary location
        rm_content = await rm_file.read()
        temp_rm_path = Path(f"/tmp/{rm_file.filename}")
        temp_rm_path.write_bytes(rm_content)

        # Initialize services
        converter = RMConverter()
        ocr_service = OCRService()

        # Check if file has content
        if not converter.has_content(temp_rm_path):
            logger.warning(f"File {rm_file.filename} has no content")
            return ProcessRMFileResponse(
                success=True,
                extracted_text="",
                page_count=0,
                metadata=None,
            )

        # Convert .rm to PDF
        logger.info(f"Converting {rm_file.filename} to PDF")
        pdf_bytes = converter.rm_to_pdf_bytes(temp_rm_path)

        # Extract text via Claude Vision OCR
        logger.info(f"Extracting text from {rm_file.filename} via OCR")
        extracted_text = await ocr_service.extract_text_from_pdf(pdf_bytes)

        # Parse metadata if provided
        metadata_dict = None
        if metadata_file:
            try:
                metadata_content = await metadata_file.read()
                parser = RMMetadataParser()
                metadata = parser.parse_bytes(metadata_content)
                metadata_dict = {
                    "visible_name": metadata.visible_name,
                    "document_type": metadata.document_type,
                    "parent": metadata.parent,
                    "last_modified": metadata.last_modified.isoformat(),
                    "version": metadata.version,
                    "pinned": metadata.pinned,
                }
                logger.info(f"Parsed metadata: {metadata.visible_name}")
            except Exception as e:
                logger.warning(f"Failed to parse metadata file: {e}")

        # Clean up temp file
        temp_rm_path.unlink(missing_ok=True)

        logger.info(
            f"Successfully processed {rm_file.filename}: "
            f"extracted {len(extracted_text)} characters"
        )

        return ProcessRMFileResponse(
            success=True,
            extracted_text=extracted_text,
            page_count=1,  # .rm files are single pages
            metadata=metadata_dict,
        )

    except Exception as e:
        logger.error(f"Failed to process .rm file: {e}", exc_info=True)
        # Clean up temp file on error
        if "temp_rm_path" in locals():
            Path(temp_rm_path).unlink(missing_ok=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to process .rm file: {str(e)}"
        )
