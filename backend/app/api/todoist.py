"""API endpoints for Todoist OAuth flow and project management."""

import base64
import hashlib
import hmac
import json
import logging
import time
from typing import List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.clerk import get_clerk_active_user
from app.config import get_settings
from app.database import get_db
from app.models.sync_record import IntegrationConfig, SyncQueue, SyncRecord
from app.models.user import User
from app.services.todoist_oauth import TodoistOAuthService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/todoist", tags=["todoist"])

_OAUTH_STATE_EXPIRY_SECONDS = 600  # 10 minutes


def _create_oauth_state(user_id: int, secret_key: str) -> str:
    """Create an HMAC-signed OAuth state token encoding user_id and expiration."""
    payload = json.dumps({"uid": user_id, "exp": int(time.time()) + _OAUTH_STATE_EXPIRY_SECONDS})
    payload_b64 = base64.urlsafe_b64encode(payload.encode()).decode()
    signature = hmac.new(secret_key.encode(), payload_b64.encode(), hashlib.sha256).hexdigest()
    return f"{payload_b64}.{signature}"


def _validate_oauth_state(state: str, secret_key: str) -> Optional[int]:
    """Validate an HMAC-signed OAuth state token. Returns user_id if valid, None otherwise."""
    try:
        parts = state.split(".")
        if len(parts) != 2:
            return None
        payload_b64, signature = parts
        expected_sig = hmac.new(secret_key.encode(), payload_b64.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected_sig):
            return None
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        if payload.get("exp", 0) < int(time.time()):
            return None
        return payload.get("uid")
    except Exception:
        return None


# --- Pydantic Models ---


class OAuthUrlResponse(BaseModel):
    authorization_url: str
    state: str


class OAuthCallbackRequest(BaseModel):
    code: str
    state: str


class OAuthCallbackResponse(BaseModel):
    success: bool
    message: str


class TodoistProject(BaseModel):
    id: str
    name: str
    is_inbox_project: bool = False


class SetProjectRequest(BaseModel):
    project_id: str
    project_name: str


class TodoistStatusResponse(BaseModel):
    connected: bool
    project_name: Optional[str] = None
    project_id: Optional[str] = None
    last_sync: Optional[str] = None
    todos_synced: int = 0


# --- Endpoints ---


@router.get("/oauth/authorize", response_model=OAuthUrlResponse)
async def get_authorization_url(
    current_user: User = Depends(get_clerk_active_user),
):
    """Generate Todoist OAuth authorization URL."""
    try:
        oauth_service = TodoistOAuthService()
        settings = get_settings()
        state = _create_oauth_state(current_user.id, settings.secret_key)
        authorization_url = oauth_service.get_authorization_url(state)
        return OAuthUrlResponse(authorization_url=authorization_url, state=state)
    except Exception as e:
        logger.error(f"Error generating Todoist OAuth URL: {e}")
        raise HTTPException(status_code=500, detail="An internal error occurred")


@router.post("/oauth/callback", response_model=OAuthCallbackResponse)
async def oauth_callback(
    request: OAuthCallbackRequest,
    current_user: User = Depends(get_clerk_active_user),
    db: Session = Depends(get_db),
):
    """Handle OAuth callback from Todoist. Exchanges code for access token."""
    try:
        settings = get_settings()

        # Validate state
        state_user_id = _validate_oauth_state(request.state, settings.secret_key)
        if state_user_id is None or state_user_id != current_user.id:
            raise HTTPException(status_code=400, detail="Invalid or expired OAuth state")

        # Exchange code for token
        oauth_service = TodoistOAuthService()
        token_data = await oauth_service.exchange_code_for_token(request.code)
        access_token = token_data["access_token"]

        # Check if integration already exists
        existing = (
            db.query(IntegrationConfig)
            .filter(
                IntegrationConfig.user_id == current_user.id,
                IntegrationConfig.target_name == "todoist",
            )
            .first()
        )

        if existing:
            config_dict = existing.get_config()
            config_dict["access_token"] = access_token
            existing.set_config(config_dict)
        else:
            config = IntegrationConfig(
                user_id=current_user.id,
                target_name="todoist",
                is_enabled=False,  # Enabled after project selection
            )
            config.set_config({"access_token": access_token})
            db.add(config)

        db.commit()
        logger.info(f"Todoist OAuth completed for user {current_user.id}")

        return OAuthCallbackResponse(success=True, message="Successfully connected to Todoist")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in Todoist OAuth callback: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An internal error occurred")


@router.get("/projects", response_model=List[TodoistProject])
async def list_projects(
    current_user: User = Depends(get_clerk_active_user),
    db: Session = Depends(get_db),
):
    """List user's Todoist projects for project selection."""
    config = (
        db.query(IntegrationConfig)
        .filter(
            IntegrationConfig.user_id == current_user.id,
            IntegrationConfig.target_name == "todoist",
        )
        .first()
    )

    if not config:
        raise HTTPException(status_code=404, detail="Todoist not connected. Complete OAuth first.")

    config_dict = config.get_config()
    access_token = config_dict.get("access_token")
    if not access_token:
        raise HTTPException(status_code=400, detail="No access token. Please reconnect.")

    try:
        oauth_service = TodoistOAuthService()
        projects = await oauth_service.list_projects(access_token)
        return [
            TodoistProject(
                id=str(p["id"]),
                name=p["name"],
                is_inbox_project=p.get("inbox_project", p.get("is_inbox_project", False)),
            )
            for p in projects
        ]
    except Exception as e:
        logger.error(f"Error listing Todoist projects: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch projects from Todoist")


class CreateProjectRequest(BaseModel):
    name: str = "reMarkable Notes"


@router.post("/projects/create", response_model=TodoistProject)
async def create_project(
    request: CreateProjectRequest,
    current_user: User = Depends(get_clerk_active_user),
    db: Session = Depends(get_db),
):
    """Create a new Todoist project."""
    config = (
        db.query(IntegrationConfig)
        .filter(
            IntegrationConfig.user_id == current_user.id,
            IntegrationConfig.target_name == "todoist",
        )
        .first()
    )

    if not config:
        raise HTTPException(status_code=404, detail="Todoist not connected. Complete OAuth first.")

    config_dict = config.get_config()
    access_token = config_dict.get("access_token")
    if not access_token:
        raise HTTPException(status_code=400, detail="No access token. Please reconnect.")

    try:
        oauth_service = TodoistOAuthService()
        project = await oauth_service.create_project(access_token, request.name)
        return TodoistProject(
            id=str(project["id"]),
            name=project["name"],
            is_inbox_project=False,
        )
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 403:
            error_data = e.response.json() if e.response.text else {}
            if error_data.get("error_tag") == "MAX_PROJECTS_LIMIT_REACHED":
                raise HTTPException(status_code=400, detail="Project limit reached in Todoist. Please select an existing project or upgrade your Todoist plan.")
        logger.error(f"Error creating Todoist project: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to create project in Todoist")
    except Exception as e:
        logger.error(f"Error creating Todoist project: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to create project in Todoist")


@router.post("/project")
async def set_project(
    request: SetProjectRequest,
    current_user: User = Depends(get_clerk_active_user),
    db: Session = Depends(get_db),
):
    """Set the target Todoist project for syncing todos."""
    config = (
        db.query(IntegrationConfig)
        .filter(
            IntegrationConfig.user_id == current_user.id,
            IntegrationConfig.target_name == "todoist",
        )
        .first()
    )

    if not config:
        raise HTTPException(status_code=404, detail="Todoist not connected. Complete OAuth first.")

    config_dict = config.get_config()
    config_dict["project_id"] = request.project_id
    config_dict["project_name"] = request.project_name
    config.set_config(config_dict)
    config.is_enabled = True
    db.commit()

    logger.info(
        f"Todoist project set for user {current_user.id}: "
        f"{request.project_name} ({request.project_id})"
    )

    return {"success": True, "message": f"Project '{request.project_name}' selected"}


@router.get("/status", response_model=TodoistStatusResponse)
async def get_status(
    current_user: User = Depends(get_clerk_active_user),
    db: Session = Depends(get_db),
):
    """Get Todoist integration status."""
    config = (
        db.query(IntegrationConfig)
        .filter(
            IntegrationConfig.user_id == current_user.id,
            IntegrationConfig.target_name == "todoist",
        )
        .first()
    )

    if not config:
        return TodoistStatusResponse(connected=False)

    config_dict = config.get_config()

    # Count synced todos
    todos_synced = (
        db.query(SyncRecord)
        .filter(
            SyncRecord.user_id == current_user.id,
            SyncRecord.target_name == "todoist",
            SyncRecord.item_type == "todo",
            SyncRecord.status == "success",
        )
        .count()
    )

    return TodoistStatusResponse(
        connected=config.is_enabled,
        project_name=config_dict.get("project_name"),
        project_id=config_dict.get("project_id"),
        last_sync=config.last_synced_at.isoformat() if config.last_synced_at else None,
        todos_synced=todos_synced,
    )


@router.delete("/disconnect")
async def disconnect(
    current_user: User = Depends(get_clerk_active_user),
    db: Session = Depends(get_db),
):
    """Disconnect Todoist integration."""
    config = (
        db.query(IntegrationConfig)
        .filter(
            IntegrationConfig.user_id == current_user.id,
            IntegrationConfig.target_name == "todoist",
        )
        .first()
    )

    if not config:
        raise HTTPException(status_code=404, detail="Todoist integration not found")

    # Clear sync records and pending queue items
    db.query(SyncRecord).filter(
        SyncRecord.user_id == current_user.id,
        SyncRecord.target_name == "todoist",
    ).delete()

    db.query(SyncQueue).filter(
        SyncQueue.user_id == current_user.id,
        SyncQueue.target_name == "todoist",
        SyncQueue.status.in_(["pending", "processing", "failed"]),
    ).delete()

    db.delete(config)
    db.commit()

    logger.info(f"Todoist disconnected for user {current_user.id}")
    return {"success": True, "message": "Todoist disconnected"}
