"""Quota API endpoints for checking and managing user quotas."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.clerk import get_clerk_active_user
from app.database import get_db
from app.models.user import User
from app.services import quota_service

logger = logging.getLogger(__name__)
router = APIRouter(tags=["quota"])


class QuotaStatusResponse(BaseModel):
    """Response model for quota status."""

    limit: int
    used: int
    remaining: int
    percentage_used: float
    is_exhausted: bool
    is_near_limit: bool
    reset_at: str
    period_start: str
    quota_type: str
    is_beta: bool = False


@router.get("/status", response_model=QuotaStatusResponse)
async def get_quota_status(
    quota_type: str = "ocr",
    current_user: User = Depends(get_clerk_active_user),
    db: Session = Depends(get_db),
):
    """
    Get current quota status for the authenticated user.

    Returns detailed information about quota usage including:
    - Current usage and limit
    - Percentage used
    - Whether quota is exhausted or near limit
    - Reset date

    Args:
        quota_type: Type of quota to check (default: 'ocr')
        current_user: Authenticated user
        db: Database session

    Returns:
        QuotaStatusResponse with current quota status

    Example:
        GET /api/quota/status
        Response: {
            "limit": 30,
            "used": 15,
            "remaining": 15,
            "percentage_used": 50.0,
            "is_exhausted": false,
            "is_near_limit": false,
            "reset_at": "2026-02-03T12:00:00",
            "period_start": "2026-01-03T12:00:00",
            "quota_type": "ocr"
        }
    """
    try:
        status = quota_service.get_quota_status(db, current_user.id, quota_type)
        return QuotaStatusResponse(**status)
    except Exception as e:
        logger.error(f"Failed to get quota status for user {current_user.id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get quota status: {str(e)}"
        )


class CheckQuotaResponse(BaseModel):
    """Response model for quota check."""

    has_quota: bool
    message: Optional[str] = None


@router.get("/check", response_model=CheckQuotaResponse)
async def check_quota(
    amount: int = 1,
    quota_type: str = "ocr",
    current_user: User = Depends(get_clerk_active_user),
    db: Session = Depends(get_db),
):
    """
    Check if user has sufficient quota available.

    Args:
        amount: Amount of quota needed (default: 1)
        quota_type: Type of quota to check (default: 'ocr')
        current_user: Authenticated user
        db: Database session

    Returns:
        CheckQuotaResponse indicating if quota is available

    Example:
        GET /api/quota/check?amount=1
        Response: {
            "has_quota": true,
            "message": null
        }
    """
    try:
        has_quota = quota_service.check_quota(db, current_user.id, quota_type, amount)

        message = None
        if not has_quota:
            status = quota_service.get_quota_status(db, current_user.id, quota_type)
            message = (
                f"Quota exceeded: {status['used']}/{status['limit']} pages used. "
                f"Resets on {status['reset_at']}."
            )

        return CheckQuotaResponse(
            has_quota=has_quota,
            message=message
        )
    except Exception as e:
        logger.error(f"Failed to check quota for user {current_user.id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to check quota: {str(e)}"
        )
