"""Agent registration and status endpoints."""

import logging
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.clerk import get_clerk_active_user
from app.config import get_settings
from app.database import get_db
from app.models.notebook import Notebook
from app.models.user import OnboardingState, User
from app.utils.umami import track_event

logger = logging.getLogger(__name__)

router = APIRouter()


class AgentRegistrationRequest(BaseModel):
    """Agent registration request."""

    version: str
    platform: str
    hostname: str | None = None


class AgentHeartbeatRequest(BaseModel):
    """Agent heartbeat request."""

    agent_id: str


@router.post("/register")
async def register_agent(
    request: AgentRegistrationRequest,
    current_user: Annotated[User, Depends(get_clerk_active_user)],
    db: Session = Depends(get_db),
):
    """
    Register a new agent instance.

    Args:
        request: Agent registration details
        current_user: Current authenticated user
        db: Database session

    Returns:
        Agent ID and status
    """
    logger.info(
        f"Agent registration request from user {current_user.email} "
        f"(ID: {current_user.id}, version: {request.version}, "
        f"platform: {request.platform}, hostname: {request.hostname})"
    )

    now = datetime.utcnow()

    # Generate a simple agent ID (user_id + timestamp)
    agent_id = f"agent_{current_user.id}_{int(now.timestamp())}"

    # Update user's onboarding state if this is first connection
    if not current_user.agent_first_connected_at:
        logger.info(f"First agent connection for user {current_user.email}")
        current_user.agent_first_connected_at = now
        await track_event(
            "agent_connected",
            {"version": request.version, "platform": request.platform},
            user_id=current_user.id,
        )

        # Update onboarding state
        if current_user.onboarding_state in [
            OnboardingState.SIGNED_UP.value,
            OnboardingState.AGENT_DOWNLOADED.value,
        ]:
            old_state = current_user.onboarding_state
            current_user.onboarding_state = OnboardingState.AGENT_CONNECTED.value
            logger.info(
                f"Updated onboarding state for {current_user.email}: "
                f"{old_state} -> {OnboardingState.AGENT_CONNECTED.value}"
            )
    else:
        logger.info(f"Repeat agent registration for user {current_user.email}")

    db.commit()

    logger.info(f"Agent registered successfully: {agent_id}")

    return {
        "agent_id": agent_id,
        "message": "Agent registered successfully",
        "user_id": current_user.id,
    }


@router.post("/heartbeat")
async def agent_heartbeat(
    request: AgentHeartbeatRequest,
    current_user: Annotated[User, Depends(get_clerk_active_user)],
    db: Session = Depends(get_db),
):
    """
    Agent heartbeat to indicate it's still running.

    Args:
        request: Heartbeat details
        current_user: Current authenticated user
        db: Database session

    Returns:
        Success message
    """
    # For now, just acknowledge the heartbeat
    # In future, we can store this in a separate agents table
    return {
        "message": "Heartbeat received",
        "timestamp": datetime.utcnow().isoformat(),
    }


class AgentStatusResponse(BaseModel):
    """Response of GET /agents/status."""

    has_agent_connected: bool
    first_connected_at: str | None
    last_activity_at: str | None
    onboarding_state: str | None


@router.get("/status", response_model=AgentStatusResponse)
async def get_agent_status(
    current_user: Annotated[User, Depends(get_clerk_active_user)],
    db: Session = Depends(get_db),
):
    """
    Get current agent connection status.

    ``last_activity_at`` is the newest ``last_synced_at`` of the user's
    notebooks: the last time the Mac app synced anything, including
    notebook metadata only (POST /sync/metadata bumps it before any page is
    uploaded). Soft-deleted notebooks still count. There is no stored
    heartbeat, so an app that runs but has nothing new to sync looks the
    same as one that stopped.

    Args:
        current_user: Current authenticated user
        db: Database session

    Returns:
        Agent connection status
    """
    has_connected = current_user.agent_first_connected_at is not None
    last_activity = db.execute(
        select(func.max(Notebook.last_synced_at)).where(Notebook.user_id == current_user.id)
    ).scalar()

    return AgentStatusResponse(
        has_agent_connected=has_connected,
        first_connected_at=current_user.agent_first_connected_at.isoformat()
        if current_user.agent_first_connected_at
        else None,
        last_activity_at=_utc_iso(last_activity),
        onboarding_state=current_user.onboarding_state,
    )


def _utc_iso(value: datetime | None) -> str | None:
    """ISO 8601 with an explicit UTC offset (columns store naive UTC)."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.isoformat() + "Z"
    return value.isoformat()


@router.get("/latest-version")
async def get_latest_agent_version():
    """Return the latest agent version and download URLs. Public endpoint."""
    settings = get_settings()
    version = settings.agent_latest_version
    macos_url = settings.agent_download_url_macos
    if not macos_url:
        macos_url = f"https://f000.backblazeb2.com/file/rmirror-downloads/releases/v{version}/rMirror-{version}.dmg"

    return {
        "version": version,
        "platforms": {
            "macos": {
                "url": macos_url,
                "min_os": "12.0",
            },
        },
    }


@router.get("/clerk-config")
async def get_clerk_config():
    """Return Clerk publishable key for agent auth bridge. Public endpoint."""
    settings = get_settings()
    return {"clerk_publishable_key": settings.clerk_publishable_key}
