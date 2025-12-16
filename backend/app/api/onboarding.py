"""Onboarding tracking endpoints."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import get_current_active_user
from app.database import get_db
from app.models.user import OnboardingState, User

router = APIRouter()


class OnboardingProgressRequest(BaseModel):
    """Request to update onboarding progress."""

    state: OnboardingState


class OnboardingProgressResponse(BaseModel):
    """Response with current onboarding state."""

    state: OnboardingState
    onboarding_started_at: datetime | None
    onboarding_completed_at: datetime | None
    agent_downloaded_at: datetime | None
    agent_first_connected_at: datetime | None


@router.get("/progress", response_model=OnboardingProgressResponse)
async def get_onboarding_progress(
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    """
    Get current user's onboarding progress.

    Args:
        current_user: Current authenticated user

    Returns:
        Current onboarding state and timestamps
    """
    return OnboardingProgressResponse(
        state=OnboardingState(current_user.onboarding_state),
        onboarding_started_at=current_user.onboarding_started_at,
        onboarding_completed_at=current_user.onboarding_completed_at,
        agent_downloaded_at=current_user.agent_downloaded_at,
        agent_first_connected_at=current_user.agent_first_connected_at,
    )


@router.post("/progress", response_model=OnboardingProgressResponse)
async def update_onboarding_progress(
    request: OnboardingProgressRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Session = Depends(get_db),
):
    """
    Update user's onboarding progress.

    Args:
        request: New onboarding state
        current_user: Current authenticated user
        db: Database session

    Returns:
        Updated onboarding state and timestamps
    """
    now = datetime.utcnow()

    # Update state
    current_user.onboarding_state = request.state.value

    # Update timestamps based on state
    if request.state == OnboardingState.SIGNED_UP and not current_user.onboarding_started_at:
        current_user.onboarding_started_at = now

    elif request.state == OnboardingState.AGENT_DOWNLOADED and not current_user.agent_downloaded_at:
        current_user.agent_downloaded_at = now

    elif request.state == OnboardingState.AGENT_CONNECTED and not current_user.agent_first_connected_at:
        current_user.agent_first_connected_at = now

    elif request.state == OnboardingState.COMPLETE and not current_user.onboarding_completed_at:
        current_user.onboarding_completed_at = now

    db.commit()
    db.refresh(current_user)

    return OnboardingProgressResponse(
        state=OnboardingState(current_user.onboarding_state),
        onboarding_started_at=current_user.onboarding_started_at,
        onboarding_completed_at=current_user.onboarding_completed_at,
        agent_downloaded_at=current_user.agent_downloaded_at,
        agent_first_connected_at=current_user.agent_first_connected_at,
    )


@router.post("/agent-downloaded")
async def track_agent_download(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Session = Depends(get_db),
):
    """
    Track when user downloads the agent.

    Args:
        current_user: Current authenticated user
        db: Database session

    Returns:
        Success message
    """
    now = datetime.utcnow()

    if not current_user.agent_downloaded_at:
        current_user.agent_downloaded_at = now

    # Update state if still at SIGNED_UP
    if current_user.onboarding_state == OnboardingState.SIGNED_UP.value:
        current_user.onboarding_state = OnboardingState.AGENT_DOWNLOADED.value

    db.commit()

    return {"message": "Agent download tracked successfully"}
