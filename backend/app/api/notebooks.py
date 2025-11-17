"""Notebook management endpoints."""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.auth import get_current_active_user
from app.database import get_db
from app.dependencies import get_storage_service
from app.models.notebook import Notebook
from app.models.user import User
from app.schemas.notebook import Notebook as NotebookSchema
from app.schemas.notebook import NotebookUploadResponse
from app.storage import StorageService
from app.utils.files import calculate_file_hash, get_document_type, validate_file_type

router = APIRouter()


@router.post("/upload", response_model=NotebookUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_notebook(
    file: UploadFile = File(...),
    current_user: Annotated[User, Depends(get_current_active_user)] = None,
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
    from io import BytesIO

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

    return NotebookUploadResponse(
        notebook=notebook,
        message="File uploaded successfully",
    )


@router.get("/", response_model=list[NotebookSchema])
async def list_notebooks(
    current_user: Annotated[User, Depends(get_current_active_user)],
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


@router.get("/uuid/{notebook_uuid}", response_model=NotebookSchema)
async def get_notebook_by_uuid(
    notebook_uuid: str,
    current_user: Annotated[User, Depends(get_current_active_user)],
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


@router.get("/{notebook_id}", response_model=NotebookSchema)
async def get_notebook(
    notebook_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[Session, Depends(get_db)],
):
    """
    Get a specific notebook by ID.

    Args:
        notebook_id: Notebook ID
        current_user: Current authenticated user
        db: Database session

    Returns:
        Notebook record
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

    return notebook


@router.delete("/{notebook_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_notebook(
    notebook_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
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
