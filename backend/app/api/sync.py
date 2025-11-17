"""API endpoints for sync operations."""

import json
import logging
from datetime import datetime
from typing import List

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_active_user
from app.core.sync_engine import SyncItem
from app.core.unified_sync_manager import UnifiedSyncManager
from app.database import get_db
from app.integrations.notion_sync import NotionSyncTarget
from app.models.sync_record import IntegrationConfig, SyncItemType
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter(tags=["sync"])


class SyncRequest(BaseModel):
    """Request to trigger a sync operation."""

    target_name: str  # "notion", "readwise", "all"
    item_type: str | None = None  # "notebook", "todo", "highlight" or None for all
    limit: int = 100
    notebook_uuids: list[str] | None = None  # Optional list of specific notebook UUIDs to sync


class SyncResponse(BaseModel):
    """Response from a sync operation."""

    success: bool
    message: str
    synced_count: int
    failed_count: int
    skipped_count: int


class SyncStatsResponse(BaseModel):
    """Sync statistics response."""

    target_name: str
    total_records: int
    status_counts: dict
    target_counts: dict
    type_counts: dict


@router.post("/trigger", response_model=SyncResponse)
async def trigger_sync(
    request: SyncRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Trigger a sync operation.

    This will sync content to the specified target (or all targets if "all" is specified).
    The sync runs in the background.
    """
    try:
        # Initialize sync manager
        sync_manager = UnifiedSyncManager(db, current_user.id)

        # Get integration configs for the user
        if request.target_name == "all":
            configs = (
                db.query(IntegrationConfig)
                .filter(
                    IntegrationConfig.user_id == current_user.id,
                    IntegrationConfig.is_enabled == True,
                )
                .all()
            )
        else:
            config = (
                db.query(IntegrationConfig)
                .filter(
                    IntegrationConfig.user_id == current_user.id,
                    IntegrationConfig.target_name == request.target_name,
                    IntegrationConfig.is_enabled == True,
                )
                .first()
            )

            if not config:
                raise HTTPException(
                    status_code=404,
                    detail=f"Integration '{request.target_name}' not found or disabled",
                )

            configs = [config]

        if not configs:
            raise HTTPException(
                status_code=404, detail="No enabled integrations found"
            )

        # Register sync targets
        for config in configs:
            config_dict = json.loads(config.config_json)

            if config.target_name == "notion":
                target = NotionSyncTarget(
                    api_token=config_dict.get("api_token"),
                    database_id=config_dict.get("database_id"),
                )
                sync_manager.register_target(target)

        # Start sync in background
        background_tasks.add_task(
            _run_sync,
            sync_manager,
            request.target_name,
            request.limit,
            current_user.id,
            db,
            request.notebook_uuids,
        )

        return SyncResponse(
            success=True,
            message=f"Sync started for {request.target_name}",
            synced_count=0,
            failed_count=0,
            skipped_count=0,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error triggering sync: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


async def _run_sync(
    sync_manager: UnifiedSyncManager,
    target_name: str,
    limit: int,
    user_id: int,
    db: Session,
    notebook_uuids: list[str] | None = None,
):
    """
    Run sync operation in background.

    Args:
        sync_manager: Initialized sync manager
        target_name: Target to sync to
        limit: Maximum items to sync
        user_id: User ID
        db: Database session
        notebook_uuids: Optional list of specific notebook UUIDs to sync
    """
    try:
        logger.info(f"Starting background sync for user {user_id} to {target_name}")

        synced_count = 0
        failed_count = 0
        skipped_count = 0

        # Get targets to sync to
        if target_name == "all":
            target_names = list(sync_manager.targets.keys())
        else:
            target_names = [target_name]

        # Get notebooks needing sync
        for t_name in target_names:
            if notebook_uuids:
                # Sync specific notebooks
                notebooks = sync_manager.get_specific_notebooks(t_name, notebook_uuids)
            else:
                # Sync notebooks that need syncing
                notebooks = sync_manager.get_notebooks_needing_sync(t_name, limit)

            logger.info(f"Found {len(notebooks)} notebooks to sync to {t_name}")

            for notebook_item in notebooks:
                result = await sync_manager.sync_item_to_target(notebook_item, t_name)

                if result.success:
                    synced_count += 1
                elif result.status.value == "skipped":
                    skipped_count += 1
                else:
                    failed_count += 1

            # Update last_synced_at
            config = (
                db.query(IntegrationConfig)
                .filter(
                    IntegrationConfig.user_id == user_id,
                    IntegrationConfig.target_name == t_name,
                )
                .first()
            )
            if config:
                config.last_synced_at = datetime.utcnow()
                db.commit()

        logger.info(
            f"Background sync completed: {synced_count} synced, {failed_count} failed, {skipped_count} skipped"
        )

    except Exception as e:
        logger.error(f"Error in background sync: {e}", exc_info=True)


@router.get("/stats", response_model=SyncStatsResponse)
async def get_sync_stats(
    target_name: str | None = None,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Get sync statistics.

    Returns statistics about sync operations for the current user.
    """
    try:
        sync_manager = UnifiedSyncManager(db, current_user.id)
        stats = sync_manager.get_sync_stats(target_name)

        return SyncStatsResponse(
            target_name=stats.get("target_name", "all"),
            total_records=stats.get("total_records", 0),
            status_counts=stats.get("status_counts", {}),
            target_counts=stats.get("target_counts", {}),
            type_counts=stats.get("type_counts", {}),
        )

    except Exception as e:
        logger.error(f"Error getting sync stats: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status/{target_name}")
async def get_sync_status(
    target_name: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Get detailed sync status for a specific target.

    Returns information about recent sync operations and any errors.
    """
    try:
        sync_manager = UnifiedSyncManager(db, current_user.id)
        stats = sync_manager.get_sync_stats(target_name)

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

        return {
            "target_name": target_name,
            "is_enabled": config.is_enabled,
            "last_synced_at": config.last_synced_at.isoformat()
            if config.last_synced_at
            else None,
            "stats": stats,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting sync status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
