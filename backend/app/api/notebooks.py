"""Notebook management endpoints."""

import json
import logging
import re
import uuid
from datetime import datetime
from io import BytesIO
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.auth.clerk import get_clerk_active_user
from app.core.pdf_service import PDFService
from app.database import get_db
from app.dependencies import get_storage_service
from app.models.notebook import Notebook
from app.models.notebook_page import NotebookPage
from app.models.page import Page
from app.models.user import User
from app.schemas.notebook import Notebook as NotebookSchema
from app.schemas.notebook import NotebookUploadResponse, NotebookWithPages
from app.services import quota_service
from app.storage import StorageService
from app.utils.files import calculate_file_hash, get_document_type, validate_file_type

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/upload", response_model=NotebookUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_notebook(
    file: UploadFile = File(...),
    current_user: Annotated[User, Depends(get_clerk_active_user)] = None,
    db: Annotated[Session, Depends(get_db)] = None,
    storage: Annotated[StorageService, Depends(get_storage_service)] = None,
):
    """
    Upload a notebook file (PDF or EPUB).

    Args:
        file: Uploaded file
        current_user: Current authenticated user
        db: Database session
        storage: Storage service

    Returns:
        Notebook record and upload confirmation
    """
    # Validate file type
    extension = validate_file_type(file, [".pdf", ".epub"])
    document_type = get_document_type(extension)

    # Read file content
    file_content = await file.read()
    file_size = len(file_content)

    # Calculate file hash
    file_stream = BytesIO(file_content)
    file_hash = calculate_file_hash(file_stream)

    # Check if file already exists for this user
    existing_notebook = (
        db.query(Notebook)
        .filter(
            Notebook.user_id == current_user.id,
            Notebook.file_hash == file_hash,
        )
        .first()
    )

    if existing_notebook:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This file has already been uploaded",
        )

    # Generate unique notebook UUID
    notebook_uuid = str(uuid.uuid4())

    # Create storage key
    storage_key = f"users/{current_user.id}/notebooks/{notebook_uuid}{extension}"

    # Upload to storage
    file_stream.seek(0)
    await storage.upload_file(
        file_stream,
        storage_key,
        content_type=file.content_type,
    )

    # Create notebook record
    notebook = Notebook(
        user_id=current_user.id,
        notebook_uuid=notebook_uuid,
        visible_name=file.filename or f"Unnamed {document_type.upper()}",
        document_type=document_type,
        s3_key=storage_key,
        file_hash=file_hash,
        file_size=file_size,
        last_synced_at=datetime.utcnow(),
    )

    db.add(notebook)
    db.commit()
    db.refresh(notebook)

    # Track first notebook milestone
    if not current_user.first_notebook_synced_at:
        current_user.first_notebook_synced_at = datetime.utcnow()
        db.commit()

    return NotebookUploadResponse(
        notebook=notebook,
        message="File uploaded successfully",
    )


@router.get("/", response_model=list[NotebookSchema])
async def list_notebooks(
    current_user: Annotated[User, Depends(get_clerk_active_user)],
    db: Annotated[Session, Depends(get_db)],
    skip: int = 0,
    limit: int = 100,
):
    """
    List all notebooks for the current user.

    Args:
        current_user: Current authenticated user
        db: Database session
        skip: Number of records to skip
        limit: Maximum number of records to return

    Returns:
        List of notebooks
    """
    notebooks = (
        db.query(Notebook)
        .filter(Notebook.user_id == current_user.id)
        .order_by(Notebook.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    return notebooks


@router.get("/tree")
async def get_notebooks_tree(
    current_user: Annotated[User, Depends(get_clerk_active_user)],
    db: Annotated[Session, Depends(get_db)],
):
    """
    Get all notebooks organized in a tree structure by folders.

    Args:
        current_user: Current authenticated user
        db: Database session

    Returns:
        Tree structure with folders and notebooks
    """
    # Get all notebooks for the user
    all_notebooks = (
        db.query(Notebook)
        .filter(Notebook.user_id == current_user.id)
        .order_by(Notebook.visible_name)
        .all()
    )

    # Identify which notebooks have children (i.e., are folders)
    has_children = set()
    for nb in all_notebooks:
        if nb.parent_uuid:
            has_children.add(nb.parent_uuid)

    # Get preview text and sync progress for each notebook
    preview_map = {}
    sync_progress_map = {}
    for nb in all_notebooks:
        if nb.document_type == "notebook":
            # Get all pages for this notebook to calculate sync progress
            all_pages = (
                db.query(Page)
                .join(NotebookPage, NotebookPage.page_id == Page.id)
                .filter(NotebookPage.notebook_id == nb.id)
                .all()
            )

            # Calculate sync progress
            total_pages = len(all_pages)
            not_synced_count = sum(1 for p in all_pages if p.ocr_status == "not_synced")
            pending_quota_count = sum(1 for p in all_pages if p.ocr_status == "pending_quota")
            synced_count = total_pages - not_synced_count

            sync_progress_map[nb.notebook_uuid] = {
                "total_pages": total_pages,
                "synced_pages": synced_count,
                "not_synced_pages": not_synced_count,
                "pending_quota_pages": pending_quota_count,
            }

            # Get most recent page (regardless of OCR status)
            most_recent_page = (
                db.query(Page)
                .join(NotebookPage, NotebookPage.page_id == Page.id)
                .filter(NotebookPage.notebook_id == nb.id)
                .order_by(NotebookPage.page_number.desc())
                .first()
            )

            # If most recent page is pending quota or not synced, don't show preview
            # (frontend will show "OCR Pending" or "Not synced" message)
            if most_recent_page and most_recent_page.ocr_status in ["pending_quota", "not_synced"]:
                preview_map[nb.notebook_uuid] = None
            else:
                # Get most recent page with OCR text
                recent_page = (
                    db.query(Page)
                    .join(NotebookPage, NotebookPage.page_id == Page.id)
                    .filter(
                        NotebookPage.notebook_id == nb.id,
                        Page.ocr_text.isnot(None),
                        Page.ocr_text != "",
                    )
                    .order_by(NotebookPage.page_number.desc())
                    .first()
                )
                if recent_page and recent_page.ocr_text:
                    # Get first 100 characters
                    preview_text = recent_page.ocr_text.strip()
                    preview_map[nb.notebook_uuid] = preview_text[:100] + ("..." if len(preview_text) > 100 else "")

    # Build tree structure
    def build_tree_node(notebook):
        """Convert a notebook to a tree node with children."""
        node = {
            "id": notebook.id,
            "notebook_uuid": notebook.notebook_uuid,
            "visible_name": notebook.visible_name,
            "document_type": notebook.document_type,
            "parent_uuid": notebook.parent_uuid,
            "full_path": notebook.full_path,
            "created_at": notebook.created_at.isoformat() if notebook.created_at else None,
            "last_synced_at": notebook.last_synced_at.isoformat() if notebook.last_synced_at else None,
            "last_opened": notebook.last_opened.isoformat() if notebook.last_opened else None,
            "is_folder": notebook.notebook_uuid in has_children,
            "preview": preview_map.get(notebook.notebook_uuid),
            "sync_progress": sync_progress_map.get(notebook.notebook_uuid),
            "children": [],
        }
        return node

    # Create tree nodes
    tree_nodes = {}
    root_nodes = []

    # First pass: create all nodes
    for nb in all_notebooks:
        tree_nodes[nb.notebook_uuid] = build_tree_node(nb)

    # Second pass: build parent-child relationships
    for notebook_uuid, node in tree_nodes.items():
        parent_uuid = node["parent_uuid"]
        if parent_uuid and parent_uuid in tree_nodes:
            # Add to parent's children
            tree_nodes[parent_uuid]["children"].append(node)
        else:
            # Root level item
            root_nodes.append(node)

    # Sort children by name
    def sort_children(node):
        if node["children"]:
            # Sort folders first, then by name
            node["children"].sort(key=lambda x: (not x["is_folder"], x["visible_name"].lower()))
            for child in node["children"]:
                sort_children(child)

    for node in root_nodes:
        sort_children(node)

    # Sort root nodes (folders first, then by name)
    root_nodes.sort(key=lambda x: (not x["is_folder"], x["visible_name"].lower()))

    return {"tree": root_nodes, "total": len(all_notebooks)}


@router.get("/uuid/{notebook_uuid}", response_model=NotebookSchema)
async def get_notebook_by_uuid(
    notebook_uuid: str,
    current_user: Annotated[User, Depends(get_clerk_active_user)],
    db: Annotated[Session, Depends(get_db)],
):
    """
    Get a specific notebook by UUID.

    Args:
        notebook_uuid: Notebook UUID
        current_user: Current authenticated user
        db: Database session

    Returns:
        Notebook record
    """
    notebook = (
        db.query(Notebook)
        .filter(
            Notebook.notebook_uuid == notebook_uuid,
            Notebook.user_id == current_user.id,
        )
        .first()
    )

    if not notebook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notebook not found",
        )

    return notebook


@router.get("/{notebook_id}", response_model=NotebookWithPages)
async def get_notebook(
    notebook_id: int,
    current_user: Annotated[User, Depends(get_clerk_active_user)],
    db: Annotated[Session, Depends(get_db)],
):
    """
    Get a specific notebook by ID with its pages.

    Uses the notebook_pages mapping table to determine page order.

    Args:
        notebook_id: Notebook ID
        current_user: Current authenticated user
        db: Database session

    Returns:
        Notebook record with pages in correct order
    """
    # Get the notebook
    notebook = (
        db.query(Notebook)
        .filter(
            Notebook.id == notebook_id,
            Notebook.user_id == current_user.id,
        )
        .first()
    )

    if not notebook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notebook not found",
        )

    # Get pages through the mapping table (source of truth for order)
    notebook_pages = (
        db.query(NotebookPage, Page)
        .join(Page, NotebookPage.page_id == Page.id)
        .filter(NotebookPage.notebook_id == notebook.id)
        .order_by(NotebookPage.page_number)
        .all()
    )

    # Attach pages to notebook in correct order
    # Set page_number from the mapping table (since it's no longer in the pages table)
    pages = []
    for notebook_page, page in notebook_pages:
        # Temporarily set page_number attribute for serialization
        page.page_number = notebook_page.page_number
        pages.append(page)

    notebook.pages = pages

    return notebook


@router.get("/{notebook_id}/export")
async def export_notebook(
    notebook_id: int,
    format: Annotated[str, Query(description="Export format: markdown or pdf")] = "markdown",
    current_user: Annotated[User, Depends(get_clerk_active_user)] = None,
    db: Annotated[Session, Depends(get_db)] = None,
    storage: Annotated[StorageService, Depends(get_storage_service)] = None,
):
    """
    Export a notebook as Markdown or PDF.

    Requires quota to be available (like other premium features).
    Returns the combined content as a downloadable file.

    Args:
        notebook_id: Notebook ID
        format: Export format ('markdown' or 'pdf')
        current_user: Current authenticated user
        db: Database session
        storage: Storage service

    Returns:
        StreamingResponse with the exported content
    """
    # Validate format
    if format not in ("markdown", "pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid format. Must be 'markdown' or 'pdf'.",
        )

    # Check quota first (export is a premium feature like Notion sync)
    quota_status = quota_service.get_quota_status(db, current_user.id)
    if quota_status["is_exhausted"]:
        raise HTTPException(
            status_code=402,
            detail={
                "message": "Quota exceeded - export unavailable",
                "quota": quota_status,
            },
        )

    # Get the notebook
    notebook = (
        db.query(Notebook)
        .filter(
            Notebook.id == notebook_id,
            Notebook.user_id == current_user.id,
        )
        .first()
    )

    if not notebook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notebook not found",
        )

    # Get pages through the mapping table (same query as display endpoint)
    notebook_pages = (
        db.query(NotebookPage, Page)
        .join(Page, NotebookPage.page_id == Page.id)
        .filter(NotebookPage.notebook_id == notebook.id)
        .order_by(NotebookPage.page_number)
        .all()
    )

    if not notebook_pages:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notebook has no pages",
        )

    # Sanitize filename (remove special characters, limit length)
    safe_name = re.sub(r'[^\w\s-]', '', notebook.visible_name or "notebook")
    safe_name = re.sub(r'\s+', '_', safe_name)[:50]

    if format == "markdown":
        return await _export_markdown(notebook, notebook_pages, safe_name)
    else:
        return await _export_pdf(notebook, notebook_pages, safe_name, storage)


async def _export_markdown(
    notebook: Notebook,
    notebook_pages: list[tuple[NotebookPage, Page]],
    safe_name: str,
) -> StreamingResponse:
    """Generate markdown export for notebook."""
    # Check if any pages have OCR text
    has_ocr_content = any(
        page.ocr_status == "completed" and page.ocr_text
        for _, page in notebook_pages
    )

    if not has_ocr_content:
        # Determine the reason for no content
        statuses = [page.ocr_status for _, page in notebook_pages]
        if all(s == "pending_quota" for s in statuses):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No OCR text available - all pages are awaiting quota",
            )
        elif all(s == "not_synced" for s in statuses):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No OCR text available - pages have not been synced yet",
            )
        elif all(s in ("pending", "processing") for s in statuses):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No OCR text available - pages are still being processed",
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No OCR text available for export",
            )

    lines = []

    # Add notebook title
    lines.append(f"# {notebook.visible_name or 'Untitled Notebook'}")
    lines.append("")

    # Add each page
    for notebook_page, page in notebook_pages:
        lines.append(f"## Page {notebook_page.page_number}")
        lines.append("")

        # Content based on OCR status
        if page.ocr_status == "completed" and page.ocr_text:
            lines.append(page.ocr_text)
        elif page.ocr_status == "processing":
            lines.append("*[OCR processing...]*")
        elif page.ocr_status == "pending":
            lines.append("*[OCR pending]*")
        elif page.ocr_status == "failed":
            lines.append("*[OCR failed]*")
        elif page.ocr_status == "pending_quota":
            lines.append("*[OCR pending - quota exceeded]*")
        elif page.ocr_status == "not_synced":
            lines.append("*[Page not yet synced]*")
        else:
            lines.append("*[No content available]*")

        lines.append("")
        lines.append("---")
        lines.append("")

    markdown_content = "\n".join(lines)

    return StreamingResponse(
        iter([markdown_content.encode("utf-8")]),
        media_type="text/markdown",
        headers={
            "Content-Disposition": f'attachment; filename="{safe_name}.md"',
        },
    )


async def _export_pdf(
    notebook: Notebook,
    notebook_pages: list[tuple[NotebookPage, Page]],
    safe_name: str,
    storage: StorageService,
) -> StreamingResponse:
    """Generate PDF export by combining page PDFs."""
    page_pdfs = []

    for notebook_page, page in notebook_pages:
        if page.pdf_s3_key:
            try:
                pdf_bytes = await storage.download_file(page.pdf_s3_key)
                page_pdfs.append(pdf_bytes)
                continue
            except Exception as e:
                logger.warning(f"Failed to download PDF for page {page.id}: {e}")
        # No pdf_s3_key or download failed - generate placeholder
        placeholder = PDFService.create_placeholder_pdf(
            f"Page {notebook_page.page_number} - Content not available"
        )
        page_pdfs.append(placeholder)

    if not page_pdfs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No PDF pages available for export",
        )

    try:
        combined_pdf = PDFService.combine_page_pdfs(page_pdfs)
    except Exception as e:
        logger.error(f"Failed to combine PDFs: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate combined PDF",
        )

    return StreamingResponse(
        iter([combined_pdf]),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{safe_name}.pdf"',
        },
    )


@router.delete("/{notebook_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_notebook(
    notebook_id: int,
    current_user: Annotated[User, Depends(get_clerk_active_user)],
    db: Annotated[Session, Depends(get_db)],
    storage: Annotated[StorageService, Depends(get_storage_service)],
):
    """
    Delete a notebook and its associated file.

    Args:
        notebook_id: Notebook ID
        current_user: Current authenticated user
        db: Database session
        storage: Storage service
    """
    notebook = (
        db.query(Notebook)
        .filter(
            Notebook.id == notebook_id,
            Notebook.user_id == current_user.id,
        )
        .first()
    )

    if not notebook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notebook not found",
        )

    # Delete file from storage
    if notebook.s3_key:
        await storage.delete_file(notebook.s3_key)

    # Delete from database
    db.delete(notebook)
    db.commit()

    return None


@router.post("/{notebook_uuid}/content", status_code=status.HTTP_200_OK)
async def upload_content_file(
    notebook_uuid: str,
    content_file: UploadFile = File(...),
    current_user: Annotated[User, Depends(get_clerk_active_user)] = None,
    db: Annotated[Session, Depends(get_db)] = None,
):
    """
    Upload and parse a .content file to update the notebook_pages mapping table.

    This endpoint:
    1. Accepts a .content JSON file for a notebook
    2. Parses the pages array (handles both old and new formats)
    3. Updates the notebook_pages mapping table with correct page order
    4. Stores the .content JSON in the notebooks table

    Args:
        notebook_uuid: UUID of the notebook
        content_file: The .content JSON file
        current_user: Authenticated user
        db: Database session

    Returns:
        Success message with page count
    """
    # Validate file type
    if not content_file.filename or not content_file.filename.endswith(".content"):
        raise HTTPException(
            status_code=400,
            detail="Invalid file type. Expected .content file.",
        )

    # Find the notebook
    notebook = (
        db.query(Notebook)
        .filter(
            Notebook.notebook_uuid == notebook_uuid,
            Notebook.user_id == current_user.id,
        )
        .first()
    )

    if not notebook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notebook not found",
        )

    try:
        # Read and parse the .content file
        content_data = await content_file.read()
        content_json = json.loads(content_data)

        # Store the raw content JSON
        notebook.content_json = json.dumps(content_json)

        # Extract pages array (handle both old and new formats)
        pages_array = content_json.get("pages", [])

        # If pages is empty, try cPages.pages (newer format)
        if not pages_array and "cPages" in content_json:
            c_pages = content_json["cPages"].get("pages", [])
            # Extract page IDs from cPages format
            pages_array = [
                p["id"] for p in c_pages if isinstance(p, dict) and "id" in p
            ]

        # Delete existing mappings for this notebook
        db.query(NotebookPage).filter(
            NotebookPage.notebook_id == notebook.id
        ).delete()

        # Create new mappings from .content file
        pages_added = 0
        for index, page_uuid in enumerate(pages_array):
            page_number = index + 1  # 1-indexed

            # Find the page by UUID
            page = (
                db.query(Page)
                .filter(
                    Page.page_uuid == page_uuid,
                    Page.notebook_id == notebook.id,  # Ensure it belongs to this user
                )
                .first()
            )

            if page:
                # Create mapping
                notebook_page = NotebookPage(
                    notebook_id=notebook.id,
                    page_id=page.id,
                    page_number=page_number,
                )
                db.add(notebook_page)
                pages_added += 1

        db.commit()

        return {
            "success": True,
            "message": "Content file processed successfully",
            "notebook_uuid": notebook_uuid,
            "pages_in_content": len(pages_array),
            "pages_mapped": pages_added,
        }

    except json.JSONDecodeError:
        raise HTTPException(
            status_code=400,
            detail="Invalid JSON in .content file",
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Error processing .content file: {str(e)}",
        )
