"""API endpoints for Notion OAuth flow and database management."""

import logging
import secrets
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.clerk import get_clerk_active_user
from app.database import get_db
from app.models.sync_record import IntegrationConfig
from app.models.user import User
from app.services.notion_oauth import NotionOAuthService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/notion", tags=["notion-oauth"])


class OAuthUrlResponse(BaseModel):
    """Response containing OAuth authorization URL."""

    authorization_url: str
    state: str


class OAuthCallbackRequest(BaseModel):
    """Request from OAuth callback."""

    code: str
    state: str


class OAuthCallbackResponse(BaseModel):
    """Response from OAuth callback."""

    success: bool
    message: str
    workspace_name: Optional[str] = None
    workspace_id: Optional[str] = None


class NotionDatabase(BaseModel):
    """Notion database information."""

    id: str
    title: str
    url: str
    created_time: str
    last_edited_time: Optional[str] = None


class NotionPage(BaseModel):
    """Notion page information."""

    id: str
    title: str
    url: str
    created_time: str


class CreateDatabaseRequest(BaseModel):
    """Request to create a new Notion database."""

    parent_page_id: Optional[str] = None
    database_title: str = "rMirror Notebooks"
    database_type: str = "notebooks"  # "notebooks" or "todos"


class CreateDatabaseResponse(BaseModel):
    """Response from database creation."""

    database_id: str
    url: str
    title: str
    created_time: str


@router.get("/oauth/authorize", response_model=OAuthUrlResponse)
async def get_authorization_url(
    current_user: User = Depends(get_clerk_active_user),
):
    """
    Generate Notion OAuth authorization URL.

    Returns a URL that the user should visit to authorize the integration.
    The state parameter is used for CSRF protection.
    """
    try:
        oauth_service = NotionOAuthService()

        # Generate random state for CSRF protection
        state = secrets.token_urlsafe(32)

        # TODO: Store state in session/cache to validate in callback
        # For now, we'll just return it and the frontend will pass it back

        authorization_url = oauth_service.get_authorization_url(state)

        return OAuthUrlResponse(authorization_url=authorization_url, state=state)

    except Exception as e:
        logger.error(f"Error generating OAuth URL: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/oauth/callback", response_model=OAuthCallbackResponse)
async def oauth_callback(
    request: OAuthCallbackRequest,
    current_user: User = Depends(get_clerk_active_user),
    db: Session = Depends(get_db),
):
    """
    Handle OAuth callback from Notion.

    Exchanges the authorization code for an access token and stores it
    in the user's integration config.
    """
    try:
        oauth_service = NotionOAuthService()

        # TODO: Validate state parameter to prevent CSRF

        # Exchange code for token
        token_data = await oauth_service.exchange_code_for_token(request.code)

        access_token = token_data["access_token"]
        workspace_id = token_data.get("workspace_id")
        workspace_name = token_data.get("workspace_name")

        # Check if Notion integration already exists
        existing = (
            db.query(IntegrationConfig)
            .filter(
                IntegrationConfig.user_id == current_user.id,
                IntegrationConfig.target_name == "notion",
            )
            .first()
        )

        if existing:
            # Update existing config with new token
            config_dict = existing.get_config()
            config_dict["access_token"] = access_token
            config_dict["workspace_id"] = workspace_id
            config_dict["workspace_name"] = workspace_name
            existing.set_config(config_dict)
            db.commit()

            logger.info(
                f"Updated Notion OAuth token for user {current_user.id} in workspace {workspace_name}"
            )
        else:
            # Create new integration config
            config = IntegrationConfig(
                user_id=current_user.id,
                target_name="notion",
                is_enabled=False,  # Will be enabled after database is selected
            )

            # Store OAuth token (encrypted)
            config.set_config({
                "access_token": access_token,
                "workspace_id": workspace_id,
                "workspace_name": workspace_name,
            })

            db.add(config)
            db.commit()

            logger.info(
                f"Created Notion OAuth integration for user {current_user.id} in workspace {workspace_name}"
            )

        return OAuthCallbackResponse(
            success=True,
            message="Successfully connected to Notion",
            workspace_name=workspace_name,
            workspace_id=workspace_id,
        )

    except Exception as e:
        logger.error(f"Error in OAuth callback: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/databases", response_model=List[NotionDatabase])
async def list_databases(
    current_user: User = Depends(get_clerk_active_user),
    db: Session = Depends(get_db),
):
    """
    List all Notion databases the integration has access to.

    Requires the user to have completed OAuth flow first.
    """
    try:
        # Get integration config
        config = (
            db.query(IntegrationConfig)
            .filter(
                IntegrationConfig.user_id == current_user.id,
                IntegrationConfig.target_name == "notion",
            )
            .first()
        )

        if not config:
            raise HTTPException(
                status_code=404,
                detail="Notion integration not found. Please complete OAuth flow first.",
            )

        config_dict = config.get_config()
        access_token = config_dict.get("access_token")

        if not access_token:
            raise HTTPException(
                status_code=400,
                detail="No access token found. Please reconnect to Notion.",
            )

        oauth_service = NotionOAuthService()
        databases = await oauth_service.list_databases(access_token)

        return [NotionDatabase(**db) for db in databases]

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing databases: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pages", response_model=List[NotionPage])
async def list_pages(
    current_user: User = Depends(get_clerk_active_user),
    db: Session = Depends(get_db),
):
    """
    List all Notion pages the integration has access to.

    Used for selecting a parent page when creating a new database.
    """
    try:
        # Get integration config
        config = (
            db.query(IntegrationConfig)
            .filter(
                IntegrationConfig.user_id == current_user.id,
                IntegrationConfig.target_name == "notion",
            )
            .first()
        )

        if not config:
            raise HTTPException(
                status_code=404,
                detail="Notion integration not found. Please complete OAuth flow first.",
            )

        config_dict = config.get_config()
        access_token = config_dict.get("access_token")

        if not access_token:
            raise HTTPException(
                status_code=400,
                detail="No access token found. Please reconnect to Notion.",
            )

        oauth_service = NotionOAuthService()
        pages = await oauth_service.list_pages(access_token)

        return [NotionPage(**page) for page in pages]

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing pages: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/databases/create", response_model=CreateDatabaseResponse)
async def create_database(
    request: CreateDatabaseRequest,
    current_user: User = Depends(get_clerk_active_user),
    db: Session = Depends(get_db),
):
    """
    Create a new Notion database configured for rMirror sync.

    The database will have properties matching the rMirror notebook schema:
    - Name (title)
    - UUID (rich_text)
    - Path (rich_text)
    - Pages (number)
    - Synced At (date)
    - Status (select)
    """
    try:
        # Determine target_name based on database type
        target_name = "notion-todos" if request.database_type == "todos" else "notion"

        # Get or create integration config for this type
        config = (
            db.query(IntegrationConfig)
            .filter(
                IntegrationConfig.user_id == current_user.id,
                IntegrationConfig.target_name == target_name,
            )
            .first()
        )

        if not config:
            # If no integration exists for this type, create one with shared OAuth token
            # Get the other integration (notion or notion-todos) to share the token
            other_target = "notion" if request.database_type == "todos" else "notion-todos"
            other_config = (
                db.query(IntegrationConfig)
                .filter(
                    IntegrationConfig.user_id == current_user.id,
                    IntegrationConfig.target_name == other_target,
                )
                .first()
            )

            if not other_config:
                raise HTTPException(
                    status_code=404,
                    detail="Notion integration not found. Please complete OAuth flow first.",
                )

            # Create new integration config sharing the same OAuth token
            other_config_dict = other_config.get_config()
            config = IntegrationConfig(
                user_id=current_user.id,
                target_name=target_name,
                is_enabled=False,
            )
            config.set_config({
                "access_token": other_config_dict.get("access_token"),
                "workspace_id": other_config_dict.get("workspace_id"),
                "workspace_name": other_config_dict.get("workspace_name"),
            })
            db.add(config)
            db.commit()
            db.refresh(config)

        config_dict = config.get_config()
        access_token = config_dict.get("access_token")

        if not access_token:
            raise HTTPException(
                status_code=400,
                detail="No access token found. Please reconnect to Notion.",
            )

        oauth_service = NotionOAuthService()
        result = await oauth_service.create_rmirror_database(
            access_token=access_token,
            parent_page_id=request.parent_page_id,
            database_title=request.database_title,
            database_type=request.database_type,
        )

        # Update integration config with database_id
        config_dict["database_id"] = result["database_id"]
        config_dict["database_title"] = result["title"]
        config.set_config(config_dict)

        # Enable integration now that database is configured
        config.is_enabled = True

        db.commit()

        logger.info(
            f"Created Notion {request.database_type} database '{result['title']}' for {target_name} integration (user {current_user.id})"
        )

        return CreateDatabaseResponse(**result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating database: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/databases/{database_id}/select")
async def select_database(
    database_id: str,
    database_type: str = Query(default="notebooks", description="Type of database: 'notebooks' or 'todos'"),
    current_user: User = Depends(get_clerk_active_user),
    db: Session = Depends(get_db),
):
    """
    Select an existing Notion database for syncing.

    Updates the integration config to use the specified database.
    Can select database for either notebooks or todos integration.
    """
    try:
        # Determine target_name based on database type
        target_name = "notion-todos" if database_type == "todos" else "notion"

        # Get integration config
        config = (
            db.query(IntegrationConfig)
            .filter(
                IntegrationConfig.user_id == current_user.id,
                IntegrationConfig.target_name == target_name,
            )
            .first()
        )

        if not config:
            # If no integration exists for this type, create one with shared OAuth token
            # Get the other integration (notion or notion-todos) to share the token
            other_target = "notion" if database_type == "todos" else "notion-todos"
            other_config = (
                db.query(IntegrationConfig)
                .filter(
                    IntegrationConfig.user_id == current_user.id,
                    IntegrationConfig.target_name == other_target,
                )
                .first()
            )

            if not other_config:
                raise HTTPException(
                    status_code=404,
                    detail="Notion integration not found. Please complete OAuth flow first.",
                )

            # Create new integration config sharing the same OAuth token
            other_config_dict = other_config.get_config()
            config = IntegrationConfig(
                user_id=current_user.id,
                target_name=target_name,
                is_enabled=False,
            )
            config.set_config({
                "access_token": other_config_dict.get("access_token"),
                "workspace_id": other_config_dict.get("workspace_id"),
                "workspace_name": other_config_dict.get("workspace_name"),
            })
            db.add(config)
            db.commit()
            db.refresh(config)

        config_dict = config.get_config()
        access_token = config_dict.get("access_token")

        if not access_token:
            raise HTTPException(
                status_code=400,
                detail="No access token found. Please reconnect to Notion.",
            )

        # Validate database exists and is accessible
        oauth_service = NotionOAuthService()
        is_valid = await oauth_service.validate_database(access_token, database_id)

        if not is_valid:
            raise HTTPException(
                status_code=400,
                detail="Database not found or not accessible. Make sure the integration has access to this database.",
            )

        # Get database info
        db_info = await oauth_service.get_database_info(access_token, database_id)

        # Update integration config
        config_dict["database_id"] = database_id
        if db_info:
            config_dict["database_title"] = db_info["title"]

        config.set_config(config_dict)
        config.is_enabled = True  # Enable integration now that database is configured
        db.commit()

        logger.info(
            f"Selected Notion database {database_id} for {target_name} integration (user {current_user.id})"
        )

        return {
            "success": True,
            "message": "Database selected successfully",
            "database_id": database_id,
            "database_title": db_info["title"] if db_info else None,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error selecting database: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
