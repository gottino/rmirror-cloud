"""Account management endpoints: data export, data summary, and account deletion."""

import logging
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.clerk import get_clerk_active_user
from app.config import get_settings
from app.database import get_db
from app.dependencies import get_storage_service
from app.models.user import User
from app.services.account_service import AccountService
from app.storage import StorageService

logger = logging.getLogger(__name__)

router = APIRouter()


class DeleteAccountRequest(BaseModel):
    confirmation: str


@router.get("/data-summary")
async def get_data_summary(
    current_user: Annotated[User, Depends(get_clerk_active_user)],
    db: Annotated[Session, Depends(get_db)],
):
    """Get a summary of all user data (for deletion confirmation UI)."""
    summary = await AccountService.get_data_summary(current_user.id, db)
    return summary


@router.post("/export")
async def export_data(
    current_user: Annotated[User, Depends(get_clerk_active_user)],
    db: Annotated[Session, Depends(get_db)],
    storage: Annotated[StorageService, Depends(get_storage_service)],
):
    """Generate and return a ZIP file containing all user data."""
    try:
        zip_bytes = await AccountService.generate_data_export(
            current_user.id, db, storage
        )
    except Exception as e:
        logger.error(f"Failed to generate data export for user {current_user.id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate data export",
        )

    date_str = datetime.utcnow().strftime("%Y-%m-%d")
    filename = f"rmirror-export-{date_str}.zip"

    return StreamingResponse(
        iter([zip_bytes]),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete("")
async def delete_account(
    body: DeleteAccountRequest,
    current_user: Annotated[User, Depends(get_clerk_active_user)],
    db: Annotated[Session, Depends(get_db)],
    storage: Annotated[StorageService, Depends(get_storage_service)],
):
    """Permanently delete the user's account and all associated data."""
    if body.confirmation != "delete my account":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Confirmation phrase must be exactly "delete my account"',
        )

    settings = get_settings()

    try:
        summary = await AccountService.delete_account(
            user_id=current_user.id,
            db=db,
            storage=storage,
            clerk_secret_key=settings.clerk_secret_key,
        )
    except Exception as e:
        logger.error(f"Failed to delete account for user {current_user.id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete account",
        )

    return {"success": True, "summary": summary}
