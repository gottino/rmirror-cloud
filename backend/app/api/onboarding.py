"""Onboarding tracking endpoints."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import get_current_active_user
from app.database import get_db
from app.models.notebook import Notebook
from app.models.page import Page
from app.models.sync_record import IntegrationConfig
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
    first_notebook_synced_at: datetime | None
    first_ocr_completed_at: datetime | None
    notion_connected_at: datetime | None
    onboarding_dismissed: bool
    # Computed convenience fields for the dashboard
    has_notebooks: bool
    has_ocr: bool
    has_notion: bool


@router.get("/progress", response_model=OnboardingProgressResponse)
async def get_onboarding_progress(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Session = Depends(get_db),
):
    """
    Get current user's onboarding progress.

    Queries actual state from the database and auto-backfills milestone
    timestamps if the milestone happened but wasn't tracked yet.

    Args:
        current_user: Current authenticated user
        db: Database session

    Returns:
        Current onboarding state and timestamps
    """
    # Query actual milestone state from the database
    has_notebooks = db.query(Notebook).filter(Notebook.user_id == current_user.id).first() is not None
    has_ocr = (
        db.query(Page)
        .join(Notebook, Page.notebook_id == Notebook.id)
        .filter(Notebook.user_id == current_user.id, Page.ocr_status == "completed")
        .first()
        is not None
    )
    has_notion = (
        db.query(IntegrationConfig)
        .filter(
            IntegrationConfig.user_id == current_user.id,
            IntegrationConfig.target_name == "notion",
            IntegrationConfig.is_enabled.is_(True),
        )
        .first()
        is not None
    )

    # Auto-backfill milestone timestamps if needed
    now = datetime.utcnow()
    changed = False
    if has_notebooks and not current_user.first_notebook_synced_at:
        current_user.first_notebook_synced_at = now
        changed = True
    if has_ocr and not current_user.first_ocr_completed_at:
        current_user.first_ocr_completed_at = now
        changed = True
    if has_notion and not current_user.notion_connected_at:
        current_user.notion_connected_at = now
        changed = True
    if changed:
        db.commit()
        db.refresh(current_user)

    return OnboardingProgressResponse(
        state=OnboardingState(current_user.onboarding_state),
        onboarding_started_at=current_user.onboarding_started_at,
        onboarding_completed_at=current_user.onboarding_completed_at,
        agent_downloaded_at=current_user.agent_downloaded_at,
        agent_first_connected_at=current_user.agent_first_connected_at,
        first_notebook_synced_at=current_user.first_notebook_synced_at,
        first_ocr_completed_at=current_user.first_ocr_completed_at,
        notion_connected_at=current_user.notion_connected_at,
        onboarding_dismissed=current_user.onboarding_dismissed,
        has_notebooks=has_notebooks,
        has_ocr=has_ocr,
        has_notion=has_notion,
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

    # Query actual milestone state for response
    has_notebooks = db.query(Notebook).filter(Notebook.user_id == current_user.id).first() is not None
    has_ocr = (
        db.query(Page)
        .join(Notebook, Page.notebook_id == Notebook.id)
        .filter(Notebook.user_id == current_user.id, Page.ocr_status == "completed")
        .first()
        is not None
    )
    has_notion = (
        db.query(IntegrationConfig)
        .filter(
            IntegrationConfig.user_id == current_user.id,
            IntegrationConfig.target_name == "notion",
            IntegrationConfig.is_enabled.is_(True),
        )
        .first()
        is not None
    )

    return OnboardingProgressResponse(
        state=OnboardingState(current_user.onboarding_state),
        onboarding_started_at=current_user.onboarding_started_at,
        onboarding_completed_at=current_user.onboarding_completed_at,
        agent_downloaded_at=current_user.agent_downloaded_at,
        agent_first_connected_at=current_user.agent_first_connected_at,
        first_notebook_synced_at=current_user.first_notebook_synced_at,
        first_ocr_completed_at=current_user.first_ocr_completed_at,
        notion_connected_at=current_user.notion_connected_at,
        onboarding_dismissed=current_user.onboarding_dismissed,
        has_notebooks=has_notebooks,
        has_ocr=has_ocr,
        has_notion=has_notion,
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


@router.post("/dismiss")
async def dismiss_onboarding(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Session = Depends(get_db),
):
    """
    Dismiss the onboarding checklist.

    Args:
        current_user: Current authenticated user
        db: Database session

    Returns:
        Success message
    """
    current_user.onboarding_dismissed = True
    db.commit()
    return {"message": "Onboarding dismissed"}
