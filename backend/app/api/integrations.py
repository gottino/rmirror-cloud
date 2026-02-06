"""API endpoints for managing external service integrations."""

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.clerk import get_clerk_active_user
from app.database import get_db
from app.integrations.notion_sync import NotionSyncTarget
from app.integrations.notion_todos_sync import NotionTodosSyncTarget
from app.models.sync_record import IntegrationConfig, SyncQueue, SyncRecord
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter(tags=["integrations"])


class NotionIntegrationConfig(BaseModel):
    """Notion integration configuration."""

    api_token: str
    database_id: str


class IntegrationConfigRequest(BaseModel):
    """Request to create/update an integration configuration."""

    target_name: str  # "notion", "readwise", etc.
    is_enabled: bool = True
    config: dict  # Target-specific configuration


class IntegrationConfigResponse(BaseModel):
    """Integration configuration response."""

    id: int
    target_name: str
    is_enabled: bool
    created_at: str
    updated_at: str
    last_synced_at: str | None = None
    # Note: config is not returned for security (contains API keys)


class IntegrationTestResponse(BaseModel):
    """Response from testing an integration connection."""

    success: bool
    target_name: str
    message: str
    details: dict | None = None


@router.post("/", response_model=IntegrationConfigResponse)
async def create_integration(
    request: IntegrationConfigRequest,
    current_user: User = Depends(get_clerk_active_user),
    db: Session = Depends(get_db),
):
    """
    Create a new integration configuration.

    This endpoint allows users to configure integrations with external services
    like Notion, Readwise, etc.
    """
    try:
        # Check if integration already exists
        existing = (
            db.query(IntegrationConfig)
            .filter(
                IntegrationConfig.user_id == current_user.id,
                IntegrationConfig.target_name == request.target_name,
            )
            .first()
        )

        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"Integration '{request.target_name}' already exists. Use PUT to update.",
            )

        # Create new integration config with encrypted credentials
        config = IntegrationConfig(
            user_id=current_user.id,
            target_name=request.target_name,
            is_enabled=request.is_enabled,
        )
        config.set_config(request.config)

        db.add(config)
        db.commit()
        db.refresh(config)

        logger.info(
            f"Created integration {request.target_name} for user {current_user.id}"
        )

        return IntegrationConfigResponse(
            id=config.id,
            target_name=config.target_name,
            is_enabled=config.is_enabled,
            created_at=config.created_at.isoformat(),
            updated_at=config.updated_at.isoformat(),
            last_synced_at=config.last_synced_at.isoformat()
            if config.last_synced_at
            else None,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating integration: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An internal error occurred")


@router.get("/", response_model=List[IntegrationConfigResponse])
async def list_integrations(
    current_user: User = Depends(get_clerk_active_user),
    db: Session = Depends(get_db),
):
    """
    List all integration configurations for the current user.

    Returns integration metadata without sensitive configuration data.
    """
    try:
        configs = (
            db.query(IntegrationConfig)
            .filter(IntegrationConfig.user_id == current_user.id)
            .all()
        )

        return [
            IntegrationConfigResponse(
                id=config.id,
                target_name=config.target_name,
                is_enabled=config.is_enabled,
                created_at=config.created_at.isoformat(),
                updated_at=config.updated_at.isoformat(),
                last_synced_at=config.last_synced_at.isoformat()
                if config.last_synced_at
                else None,
            )
            for config in configs
        ]

    except Exception as e:
        logger.error(f"Error listing integrations: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An internal error occurred")


@router.get(
    "/{target_name}", response_model=IntegrationConfigResponse
)
async def get_integration(
    target_name: str,
    current_user: User = Depends(get_clerk_active_user),
    db: Session = Depends(get_db),
):
    """Get a specific integration configuration."""
    try:
        config = (
            db.query(IntegrationConfig)
            .filter(
                IntegrationConfig.user_id == current_user.id,
                IntegrationConfig.target_name == target_name,
            )
            .first()
        )

        if not config:
            raise HTTPException(
                status_code=404, detail=f"Integration '{target_name}' not found"
            )

        return IntegrationConfigResponse(
            id=config.id,
            target_name=config.target_name,
            is_enabled=config.is_enabled,
            created_at=config.created_at.isoformat(),
            updated_at=config.updated_at.isoformat(),
            last_synced_at=config.last_synced_at.isoformat()
            if config.last_synced_at
            else None,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting integration: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An internal error occurred")


@router.put("/{target_name}", response_model=IntegrationConfigResponse)
async def update_integration(
    target_name: str,
    request: IntegrationConfigRequest,
    current_user: User = Depends(get_clerk_active_user),
    db: Session = Depends(get_db),
):
    """Update an existing integration configuration."""
    try:
        config = (
            db.query(IntegrationConfig)
            .filter(
                IntegrationConfig.user_id == current_user.id,
                IntegrationConfig.target_name == target_name,
            )
            .first()
        )

        if not config:
            raise HTTPException(
                status_code=404, detail=f"Integration '{target_name}' not found"
            )

        # Update config with encrypted credentials
        config.is_enabled = request.is_enabled
        config.set_config(request.config)

        db.commit()
        db.refresh(config)

        logger.info(f"Updated integration {target_name} for user {current_user.id}")

        return IntegrationConfigResponse(
            id=config.id,
            target_name=config.target_name,
            is_enabled=config.is_enabled,
            created_at=config.created_at.isoformat(),
            updated_at=config.updated_at.isoformat(),
            last_synced_at=config.last_synced_at.isoformat()
            if config.last_synced_at
            else None,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating integration: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An internal error occurred")


@router.delete("/{target_name}")
async def delete_integration(
    target_name: str,
    current_user: User = Depends(get_clerk_active_user),
    db: Session = Depends(get_db),
):
    """Delete an integration configuration."""
    try:
        config = (
            db.query(IntegrationConfig)
            .filter(
                IntegrationConfig.user_id == current_user.id,
                IntegrationConfig.target_name == target_name,
            )
            .first()
        )

        if not config:
            raise HTTPException(
                status_code=404, detail=f"Integration '{target_name}' not found"
            )

        # Clear sync records and queue items for this integration
        # This ensures a fresh start if user reconnects to a different database
        records_deleted = (
            db.query(SyncRecord)
            .filter(
                SyncRecord.user_id == current_user.id,
                SyncRecord.target_name == target_name,
            )
            .delete()
        )
        queue_deleted = (
            db.query(SyncQueue)
            .filter(
                SyncQueue.user_id == current_user.id,
                SyncQueue.target_name == target_name,
                SyncQueue.status.in_(["pending", "processing", "failed"]),
            )
            .delete()
        )
        logger.info(
            f"Cleared {records_deleted} sync records and {queue_deleted} queue items "
            f"for user {current_user.id} target {target_name}"
        )

        db.delete(config)
        db.commit()

        logger.info(f"Deleted integration {target_name} for user {current_user.id}")

        return {"success": True, "message": f"Integration '{target_name}' deleted"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting integration: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An internal error occurred")


@router.post("/{target_name}/test", response_model=IntegrationTestResponse)
async def test_integration(
    target_name: str,
    current_user: User = Depends(get_clerk_active_user),
    db: Session = Depends(get_db),
):
    """
    Test an integration connection.

    Validates that the integration is properly configured and can connect
    to the external service.
    """
    try:
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
            raise HTTPException(
                status_code=404, detail=f"Integration '{target_name}' not found"
            )

        config_dict = config.get_config()  # Use encrypted config

        # Create sync target based on type
        if target_name == "notion":
            access_token = config_dict.get("access_token")
            database_id = config_dict.get("database_id")

            if not access_token or not database_id:
                raise HTTPException(
                    status_code=400,
                    detail="Notion integration requires access_token and database_id. Please reconnect to Notion.",
                )

            target = NotionSyncTarget(access_token=access_token, database_id=database_id)

        elif target_name == "notion-todos":
            # Notion todos integration - syncs to separate todos database
            access_token = config_dict.get("access_token")
            database_id = config_dict.get("database_id")
            use_status_property = config_dict.get("use_status_property", False)

            if not access_token or not database_id:
                raise HTTPException(
                    status_code=400,
                    detail="Notion Todos integration requires access_token and database_id. Please reconnect to Notion.",
                )

            target = NotionTodosSyncTarget(
                access_token=access_token,
                database_id=database_id,
                use_status_property=use_status_property,
            )

        else:
            raise HTTPException(
                status_code=400, detail=f"Unknown integration type: {target_name}"
            )

        # Test the connection
        is_valid = await target.validate_connection()
        target_info = target.get_target_info()

        if is_valid:
            return IntegrationTestResponse(
                success=True,
                target_name=target_name,
                message="Connection successful",
                details=target_info,
            )
        else:
            return IntegrationTestResponse(
                success=False,
                target_name=target_name,
                message="Connection failed",
                details=target_info,
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error testing integration: {e}", exc_info=True)
        return IntegrationTestResponse(
            success=False,
            target_name=target_name,
            message=f"Error: {str(e)}",
            details=None,
        )
