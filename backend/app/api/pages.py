"""Page management endpoints."""

from io import BytesIO
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.auth.clerk import get_clerk_active_user
from app.database import get_db
from app.dependencies import get_storage_service
from app.models.page import Page
from app.models.user import User
from app.storage import StorageService

router = APIRouter()


@router.get("/{page_id}/pdf")
async def get_page_pdf(
    page_id: int,
    current_user: Annotated[User, Depends(get_clerk_active_user)],
    db: Annotated[Session, Depends(get_db)],
    storage: Annotated[StorageService, Depends(get_storage_service)],
):
    """
    Get the PDF for a specific page.

    Args:
        page_id: Page ID
        current_user: Current authenticated user
        db: Database session
        storage: Storage service

    Returns:
        PDF file as streaming response
    """
    # Get the page and verify ownership via notebook
    page = (
        db.query(Page)
        .filter(Page.id == page_id)
        .first()
    )

    if not page:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Page not found",
        )

    # Verify user owns this page via notebook
    if page.notebook.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this page",
        )

    # Check if PDF exists
    if not page.pdf_s3_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="PDF not available for this page",
        )

    # Get PDF from storage
    try:
        pdf_bytes = await storage.download_file(page.pdf_s3_key)

        # Wrap bytes in BytesIO for streaming
        pdf_stream = BytesIO(pdf_bytes)

        # Return as streaming response
        return StreamingResponse(
            pdf_stream,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'inline; filename="page_{page.page_uuid}.pdf"'
            }
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving PDF: {str(e)}",
        )
