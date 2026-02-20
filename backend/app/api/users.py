"""User management endpoints."""

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import get_current_active_user
from app.database import get_db
from app.models.user import User
from app.schemas.user import User as UserSchema

router = APIRouter()

CURRENT_TOS_VERSION = "2026-02-20"
CURRENT_PRIVACY_VERSION = "2026-02-20"


class LegalStatusResponse(BaseModel):
    tos_accepted: bool
    privacy_accepted: bool
    tos_version: str | None
    privacy_version: str | None
    current_tos_version: str
    current_privacy_version: str


@router.get("/me", response_model=UserSchema)
async def get_current_user_info(
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    """Get current user information."""
    return current_user


@router.get("/legal-status", response_model=LegalStatusResponse)
async def get_legal_status(
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    """Check whether the user has accepted the current ToS and Privacy Policy versions."""
    return LegalStatusResponse(
        tos_accepted=current_user.tos_version == CURRENT_TOS_VERSION,
        privacy_accepted=current_user.privacy_version == CURRENT_PRIVACY_VERSION,
        tos_version=current_user.tos_version,
        privacy_version=current_user.privacy_version,
        current_tos_version=CURRENT_TOS_VERSION,
        current_privacy_version=CURRENT_PRIVACY_VERSION,
    )


@router.post("/accept-terms", response_model=LegalStatusResponse)
async def accept_terms(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[Session, Depends(get_db)],
):
    """Record acceptance of the current ToS and Privacy Policy."""
    now = datetime.now(timezone.utc)
    current_user.tos_accepted_at = now
    current_user.tos_version = CURRENT_TOS_VERSION
    current_user.privacy_accepted_at = now
    current_user.privacy_version = CURRENT_PRIVACY_VERSION
    db.commit()
    db.refresh(current_user)

    return LegalStatusResponse(
        tos_accepted=True,
        privacy_accepted=True,
        tos_version=CURRENT_TOS_VERSION,
        privacy_version=CURRENT_PRIVACY_VERSION,
        current_tos_version=CURRENT_TOS_VERSION,
        current_privacy_version=CURRENT_PRIVACY_VERSION,
    )
