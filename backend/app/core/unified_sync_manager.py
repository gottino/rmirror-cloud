"""
Sync statistics for rmirror Cloud.

Reads the unified ``sync_records`` table for the sync stats/status endpoints.
Writing to targets is the sync worker's job (``app/services/sync_worker.py``);
nothing here talks to a target.
"""

import logging
from typing import Any, Dict, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.sync_record import SyncRecord

logger = logging.getLogger(__name__)


class UnifiedSyncManager:
    """Per-user read access to sync records (statistics)."""

    def __init__(self, db: Session, user_id: int):
        """
        Initialize the sync manager.

        Args:
            db: Database session
            user_id: User ID to scope operations
        """
        self.db = db
        self.user_id = user_id
        self.logger = logging.getLogger(f"{__name__}.UnifiedSyncManager")

    def get_sync_stats(self, target_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Get sync statistics for all targets or a specific target.

        Args:
            target_name: Optional target name to filter by

        Returns:
            Dictionary with sync statistics
        """
        try:
            # Base query
            query = self.db.query(SyncRecord).filter(SyncRecord.user_id == self.user_id)

            if target_name:
                query = query.filter(SyncRecord.target_name == target_name)

            total_records = query.count()

            # Stats by status
            status_counts = {}
            status_results = (
                query.with_entities(SyncRecord.status, func.count(SyncRecord.id))
                .group_by(SyncRecord.status)
                .all()
            )
            for status, count in status_results:
                status_counts[status] = count

            # Stats by target (if not filtering)
            target_counts = {}
            if not target_name:
                target_results = (
                    self.db.query(SyncRecord)
                    .filter(SyncRecord.user_id == self.user_id)
                    .with_entities(
                        SyncRecord.target_name, func.count(SyncRecord.id)
                    )
                    .group_by(SyncRecord.target_name)
                    .all()
                )
                for t_name, count in target_results:
                    target_counts[t_name] = count
            else:
                target_counts = {target_name: total_records}

            # Stats by item type
            type_counts = {}
            type_results = (
                query.with_entities(SyncRecord.item_type, func.count(SyncRecord.id))
                .group_by(SyncRecord.item_type)
                .all()
            )
            for item_type, count in type_results:
                type_counts[item_type] = count

            return {
                "target_name": target_name or "all",
                "total_records": total_records,
                "status_counts": status_counts,
                "target_counts": target_counts,
                "type_counts": type_counts,
            }

        except Exception as e:
            self.logger.error(f"Error getting sync stats: {e}")
            return {}
