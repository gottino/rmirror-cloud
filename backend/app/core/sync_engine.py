"""
Event-Driven Sync Engine for rmirror Cloud

This module provides a robust, event-driven synchronization system that can push
content from the cloud database to multiple downstream targets (Notion, Readwise, etc.)
with intelligent deduplication and error handling.

Core Principles:
1. Cloud DB as Source of Truth - All changes flow from cloud database
2. Zero Duplicates - Robust deduplication across all downstream targets
3. Fast & Reliable - Quick sync with intelligent retry and error handling
4. Target Agnostic - Support multiple downstream apps
5. Event-Driven - React to changes immediately, not polling
"""

import hashlib
import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, Optional

from app.models.sync_record import SyncItemType, SyncStatus

logger = logging.getLogger(__name__)


# Wait this long after a rate limit when the provider gives no Retry-After.
RATE_LIMIT_DEFAULT_DELAY = timedelta(seconds=30)


class SyncErrorKind(str, Enum):
    """Why a sync attempt failed, as classified by the target itself.

    The sync worker acts on this when a target sets it, and only falls back to
    matching the error text when it is absent.
    """

    RATE_LIMITED = "rate_limited"  # retry at retry_after; does not use up a retry
    AUTH = "auth"  # token revoked or access removed: permanent for the item
    PARENT_GONE = "parent_gone"  # the notebook's page in the target is archived/missing
    PERMANENT = "permanent"  # bad request; retrying cannot help
    TRANSIENT = "transient"  # network / provider 5xx; retry with backoff


@dataclass
class SyncResult:
    """Result of a sync operation."""

    status: SyncStatus
    target_id: Optional[str] = None  # External ID in target system
    error_message: Optional[str] = None
    retry_after: Optional[datetime] = None  # naive UTC; earliest time to retry
    metadata: Dict[str, Any] = field(default_factory=dict)
    error_kind: Optional[SyncErrorKind] = None

    @property
    def success(self) -> bool:
        return self.status == SyncStatus.SUCCESS


@dataclass
class SyncItem:
    """Item to be synchronized to external targets."""

    item_type: SyncItemType
    item_id: str  # UUID or primary key in local DB
    content_hash: str  # Hash for duplicate detection
    data: Dict[str, Any]  # The actual content to sync
    source_table: str  # Which table this came from
    created_at: datetime
    updated_at: datetime


class SyncTarget(ABC):
    """
    Abstract base class for sync targets.

    Each downstream integration (Notion, Readwise, etc.) should implement this interface
    to provide a consistent way to sync content and detect duplicates.
    """

    def __init__(self, target_name: str):
        self.target_name = target_name
        self.logger = logging.getLogger(f"{__name__}.{target_name}")

    @abstractmethod
    async def sync_item(self, item: SyncItem) -> SyncResult:
        """
        Sync a single item to this target.

        Args:
            item: The item to sync

        Returns:
            SyncResult indicating success/failure and any metadata
        """
        pass

    @abstractmethod
    async def check_duplicate(self, content_hash: str) -> Optional[str]:
        """
        Check if content with this hash already exists in the target.

        Args:
            content_hash: Hash of the content to check

        Returns:
            External ID if duplicate found, None otherwise
        """
        pass

    @abstractmethod
    async def update_item(self, external_id: str, item: SyncItem) -> SyncResult:
        """
        Update an existing item in the target system.

        Args:
            external_id: ID of the item in the target system
            item: Updated item data

        Returns:
            SyncResult indicating success/failure
        """
        pass

    @abstractmethod
    async def delete_item(self, external_id: str) -> SyncResult:
        """
        Delete an item from the target system.

        Args:
            external_id: ID of the item in the target system

        Returns:
            SyncResult indicating success/failure
        """
        pass

    @abstractmethod
    def get_target_info(self) -> Dict[str, Any]:
        """
        Get information about this target for monitoring/debugging.

        Returns:
            Dictionary with target information
        """
        pass

    def generate_content_hash(self, data: Dict[str, Any]) -> str:
        """
        Generate a deterministic hash for content deduplication.

        Args:
            data: Content data to hash

        Returns:
            SHA-256 hash string
        """
        # Create a stable representation for hashing
        content_str = json.dumps(data, sort_keys=True, ensure_ascii=True)
        return hashlib.sha256(content_str.encode("utf-8")).hexdigest()

    async def validate_connection(self) -> bool:
        """
        Validate that the target is accessible and properly configured.

        Returns:
            True if connection is valid, False otherwise
        """
        try:
            info = self.get_target_info()
            return info.get("connected", False)
        except Exception as e:
            self.logger.error(
                f"Connection validation failed for {self.target_name}: {e}"
            )
            return False


class ContentFingerprint:
    """
    Service for generating consistent content fingerprints for deduplication.

    This ensures that identical content gets the same hash regardless of
    minor variations in metadata or formatting.
    """

    @staticmethod
    def for_notebook_metadata(notebook_data: Dict[str, Any]) -> str:
        """
        Generate content fingerprint for notebook metadata only (lightweight).

        This hash changes only when metadata changes, not when page content changes.
        Used for metadata-only syncs to avoid processing all page content.

        Args:
            notebook_data: Notebook metadata dictionary

        Returns:
            SHA-256 hash of the normalized metadata
        """
        # Extract only metadata fields
        title = notebook_data.get("title", notebook_data.get("notebook_name", ""))
        page_count = notebook_data.get("page_count", 0)
        full_path = notebook_data.get("full_path", "")
        last_opened_at = notebook_data.get("last_opened_at", "")
        last_modified_at = notebook_data.get("last_modified_at", "")

        # Create normalized metadata string (no content)
        # The notebook uuid is part of the hash: identical metadata of two
        # notebooks must not dedupe against each other in the sync queue.
        content_parts = [
            f"notebook:{notebook_data.get('notebook_uuid', '')}",
            f"title:{title}",
            f"pages:{page_count}",
            f"path:{full_path}",
            f"last_opened:{last_opened_at}",
            f"last_modified:{last_modified_at}",
        ]

        content_str = "|".join(content_parts)
        return hashlib.sha256(content_str.encode("utf-8")).hexdigest()

    @staticmethod
    def for_todo(todo_data: Dict[str, Any]) -> str:
        """
        Generate content fingerprint for a todo item.

        Args:
            todo_data: Todo content dictionary

        Returns:
            SHA-256 hash of the normalized content
        """
        text = todo_data.get("text", "")
        notebook_uuid = todo_data.get("notebook_uuid", "")
        page_number = todo_data.get("page_number", 0)

        content_parts = [
            f"text:{text}",
            f"notebook:{notebook_uuid}",
            f"page:{page_number}",
        ]

        content_str = "|".join(content_parts)
        return hashlib.sha256(content_str.encode("utf-8")).hexdigest()
