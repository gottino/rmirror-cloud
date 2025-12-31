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
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

from app.models.sync_record import SyncStatus, SyncItemType

logger = logging.getLogger(__name__)


@dataclass
class SyncResult:
    """Result of a sync operation."""

    status: SyncStatus
    target_id: Optional[str] = None  # External ID in target system
    error_message: Optional[str] = None
    retry_after: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def success(self) -> bool:
        return self.status == SyncStatus.SUCCESS

    @property
    def should_retry(self) -> bool:
        return self.status == SyncStatus.RETRY


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

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "item_type": self.item_type.value,
            "item_id": self.item_id,
            "content_hash": self.content_hash,
            "data": self.data,
            "source_table": self.source_table,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


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
    def for_notebook(notebook_data: Dict[str, Any]) -> str:
        """
        Generate content fingerprint for a notebook.

        Args:
            notebook_data: Notebook content dictionary

        Returns:
            SHA-256 hash of the normalized content
        """
        # Extract core content that defines uniqueness
        title = notebook_data.get("title", notebook_data.get("notebook_name", ""))
        text_content = notebook_data.get("text_content", "")
        page_count = notebook_data.get("page_count", 0)
        last_opened_at = notebook_data.get("last_opened_at", "")
        last_modified_at = notebook_data.get("last_modified_at", "")

        # Create normalized content string
        content_parts = [
            f"title:{title}",
            f"pages:{page_count}",
            f"content:{text_content[:1000]}",  # First 1000 chars to keep hash stable
            f"last_opened:{last_opened_at}",  # Include metadata timestamps
            f"last_modified:{last_modified_at}",
        ]

        content_str = "|".join(content_parts)
        return hashlib.sha256(content_str.encode("utf-8")).hexdigest()

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
        content_parts = [
            f"title:{title}",
            f"pages:{page_count}",
            f"path:{full_path}",
            f"last_opened:{last_opened_at}",
            f"last_modified:{last_modified_at}",
        ]

        content_str = "|".join(content_parts)
        return hashlib.sha256(content_str.encode("utf-8")).hexdigest()

    @staticmethod
    def for_page(page_data: Dict[str, Any]) -> str:
        """
        Generate content fingerprint for a single page.

        Args:
            page_data: Page content dictionary

        Returns:
            SHA-256 hash of the normalized content
        """
        notebook_uuid = page_data.get("notebook_uuid", "")
        page_number = page_data.get("page_number", 0)
        text = page_data.get("text", "")

        # Create normalized content string
        content_parts = [
            f"notebook:{notebook_uuid}",
            f"page:{page_number}",
            f"text:{text}",
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

    @staticmethod
    def for_highlight(highlight_data: Dict[str, Any]) -> str:
        """
        Generate content fingerprint for a highlight.

        Args:
            highlight_data: Highlight content dictionary

        Returns:
            SHA-256 hash of the normalized content
        """
        text = highlight_data.get("text", "")
        corrected_text = highlight_data.get("corrected_text", "")
        source_file = highlight_data.get("source_file", "")
        page_number = highlight_data.get("page_number", 0)

        content_parts = [
            f"text:{text}",
            f"corrected:{corrected_text}",
            f"source:{source_file}",
            f"page:{page_number}",
        ]

        content_str = "|".join(content_parts)
        return hashlib.sha256(content_str.encode("utf-8")).hexdigest()
