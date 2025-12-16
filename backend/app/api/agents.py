"""Agent registration and status endpoints."""

from datetime import datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import and_, desc
from sqlalchemy.orm import Session

from app.auth import get_current_active_user
from app.database import get_db
from app.models.user import OnboardingState, User

router = APIRouter()


class AgentRegistrationRequest(BaseModel):
    """Agent registration request."""

    version: str
    platform: str
    hostname: str | None = None


class AgentHeartbeatRequest(BaseModel):
    """Agent heartbeat request."""

    agent_id: str


class AgentStatusResponse(BaseModel):
    """Agent status response."""

    agent_id: str
    is_online: bool
    version: str
    platform: str
    hostname: str | None
    first_seen_at: datetime
    last_seen_at: datetime


@router.post("/register")
async def register_agent(
    request: AgentRegistrationRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
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
    now = datetime.utcnow()

    # Generate a simple agent ID (user_id + timestamp)
    agent_id = f"agent_{current_user.id}_{int(now.timestamp())}"

    # Update user's onboarding state if this is first connection
    if not current_user.agent_first_connected_at:
        current_user.agent_first_connected_at = now

        # Update onboarding state
        if current_user.onboarding_state in [
            OnboardingState.SIGNED_UP.value,
            OnboardingState.AGENT_DOWNLOADED.value,
        ]:
            current_user.onboarding_state = OnboardingState.AGENT_CONNECTED.value

    db.commit()

    return {
        "agent_id": agent_id,
        "message": "Agent registered successfully",
        "user_id": current_user.id,
    }


@router.post("/heartbeat")
async def agent_heartbeat(
    request: AgentHeartbeatRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
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


@router.get("/status")
async def get_agent_status(
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    """
    Get current agent connection status.

    Args:
        current_user: Current authenticated user

    Returns:
        Agent connection status
    """
    # For now, return basic status based on user data
    # In future, we can check against stored agent records
    has_connected = current_user.agent_first_connected_at is not None

    return {
        "has_agent_connected": has_connected,
        "first_connected_at": current_user.agent_first_connected_at.isoformat()
        if current_user.agent_first_connected_at
        else None,
        "onboarding_state": current_user.onboarding_state,
    }
