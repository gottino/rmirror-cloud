"""
Unified Sync Manager for rmirror Cloud.

This module provides a unified interface for managing sync operations across
multiple targets (Notion, Readwise, etc.) using a target-agnostic approach.

Key Features:
- Target-agnostic sync management using target_name
- Content-hash based change detection and deduplication
- Unified sync_records table for all targets
- Integration with SyncTarget interface
- Support for incremental and real-time sync
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from app.core.sync_engine import ContentFingerprint, SyncItem, SyncResult, SyncTarget
from app.models.notebook import Notebook
from app.models.page import Page
from app.models.sync_record import (
    IntegrationConfig,
    PageSyncRecord,
    SyncItemType,
    SyncRecord,
    SyncStatus,
)

logger = logging.getLogger(__name__)


class UnifiedSyncManager:
    """
    Unified sync manager that coordinates sync operations across all targets.

    This provides a single unified interface that can handle multiple sync
    targets using the target_name approach.
    """

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
        self.targets: Dict[str, SyncTarget] = {}

    def register_target(self, target: SyncTarget):
        """
        Register a sync target with the unified manager.

        Args:
            target: SyncTarget implementation
        """
        target_name = target.target_name
        self.targets[target_name] = target
        self.logger.info(f"Registered sync target: {target_name}")

    def unregister_target(self, target_name: str):
        """
        Unregister a sync target.

        Args:
            target_name: Name of target to unregister
        """
        if target_name in self.targets:
            del self.targets[target_name]
            self.logger.info(f"Unregistered sync target: {target_name}")

    def get_target(self, target_name: str) -> Optional[SyncTarget]:
        """
        Get a registered sync target by name.

        Args:
            target_name: Name of target to retrieve

        Returns:
            SyncTarget instance if found, None otherwise
        """
        return self.targets.get(target_name)

    async def sync_item_to_target(
        self, item: SyncItem, target_name: str
    ) -> SyncResult:
        """
        Sync a single item to a specific target.

        Args:
            item: The item to sync
            target_name: Name of the target to sync to

        Returns:
            SyncResult indicating success/failure
        """
        if target_name not in self.targets:
            return SyncResult(
                status=SyncStatus.FAILED,
                error_message=f"Target '{target_name}' not registered",
            )

        target = self.targets[target_name]

        try:
            # Calculate content hash if not provided
            if not item.content_hash:
                if hasattr(target, "calculate_content_hash"):
                    item.content_hash = target.calculate_content_hash(item)
                else:
                    # Fallback: use ContentFingerprint
                    if item.item_type == SyncItemType.NOTEBOOK:
                        item.content_hash = ContentFingerprint.for_notebook(item.data)
                    elif item.item_type == SyncItemType.PAGE_TEXT:
                        item.content_hash = ContentFingerprint.for_page(item.data)
                    elif item.item_type == SyncItemType.TODO:
                        item.content_hash = ContentFingerprint.for_todo(item.data)
                    elif item.item_type == SyncItemType.HIGHLIGHT:
                        item.content_hash = ContentFingerprint.for_highlight(item.data)

            # Check for existing sync record
            if item.item_type == SyncItemType.PAGE_TEXT:
                existing_sync = self.get_page_sync_record(item.item_id, target_name)
            else:
                existing_sync = self.get_sync_record(item.content_hash, target_name)

            if existing_sync and existing_sync["status"] == SyncStatus.SUCCESS.value:
                # Check if content has changed (for page syncs)
                if item.item_type == SyncItemType.PAGE_TEXT:
                    if existing_sync.get("content_hash") == item.content_hash:
                        self.logger.debug(
                            f"Page already synced with same content: {item.item_id}"
                        )
                        return SyncResult(
                            status=SyncStatus.SKIPPED,
                            target_id=existing_sync.get("notion_page_id", ""),
                            metadata={
                                "reason": "already_synced",
                                "content_unchanged": True,
                            },
                        )
                    else:
                        self.logger.info(
                            f"Page content changed, will re-sync: {item.item_id}"
                        )
                else:
                    # Already synced successfully (non-page items)
                    self.logger.debug(
                        f"Item already synced to {target_name}: {item.content_hash[:8]}..."
                    )
                    return SyncResult(
                        status=SyncStatus.SKIPPED,
                        target_id=existing_sync["external_id"],
                        metadata={"reason": "already_synced"},
                    )

            # Log details for debugging
            self.logger.info(f"🔄 Syncing item {item.item_id} to {target_name}")
            self.logger.info(f"   Content hash: {item.content_hash[:8]}...")
            self.logger.info(f"   Item type: {item.item_type}")

            # Attempt to sync the item
            result = await target.sync_item(item)

            # Record the sync result
            self.record_sync_result(
                content_hash=item.content_hash,
                target_name=target_name,
                item_id=item.item_id,
                item_type=item.item_type,
                result=result,
                metadata={
                    "source_table": item.source_table,
                    "created_at": item.created_at.isoformat(),
                    "updated_at": item.updated_at.isoformat(),
                },
            )

            return result

        except Exception as e:
            error_msg = f"Error syncing to {target_name}: {e}"
            self.logger.error(error_msg)

            error_result = SyncResult(
                status=SyncStatus.FAILED,
                error_message=str(e),
                metadata={
                    "item_type": item.item_type.value,
                    "item_id": item.item_id,
                    "target_name": target_name,
                    "error_type": type(e).__name__,
                },
            )

            # Record the failure
            self.record_sync_result(
                content_hash=item.content_hash,
                target_name=target_name,
                item_id=item.item_id,
                item_type=item.item_type,
                result=error_result,
            )

            return error_result

    async def sync_item_to_all_targets(
        self, item: SyncItem, exclude_targets: Optional[Set[str]] = None
    ) -> Dict[str, SyncResult]:
        """
        Sync a single item to all registered targets.

        Args:
            item: The item to sync
            exclude_targets: Set of target names to exclude

        Returns:
            Dictionary mapping target names to sync results
        """
        if exclude_targets is None:
            exclude_targets = set()

        results = {}

        for target_name in self.targets:
            if target_name in exclude_targets:
                continue

            result = await self.sync_item_to_target(item, target_name)
            results[target_name] = result

        return results

    def get_page_sync_record(
        self, item_id: str, target_name: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get sync record for a specific page from page_sync_records table.

        Args:
            item_id: Item ID in format "notebook_uuid:page:page_number"
            target_name: Name of the target

        Returns:
            Sync record dict or None if not found
        """
        try:
            # Parse item_id to extract notebook_uuid and page_number
            parts = item_id.split(":page:")
            if len(parts) != 2:
                self.logger.error(f"Invalid page item_id format: {item_id}")
                return None

            notebook_uuid = parts[0]
            page_number = int(parts[1])

            record = (
                self.db.query(PageSyncRecord)
                .filter(
                    and_(
                        PageSyncRecord.user_id == self.user_id,
                        PageSyncRecord.notebook_uuid == notebook_uuid,
                        PageSyncRecord.page_number == page_number,
                        PageSyncRecord.target_name == target_name,
                    )
                )
                .first()
            )

            if record:
                return {
                    "id": record.id,
                    "notebook_uuid": record.notebook_uuid,
                    "page_number": record.page_number,
                    "content_hash": record.content_hash,
                    "target_name": record.target_name,
                    "notion_page_id": record.notion_page_id,
                    "notion_block_id": record.notion_block_id,
                    "status": record.status,
                    "error_message": record.error_message,
                    "retry_count": record.retry_count,
                    "created_at": record.created_at.isoformat(),
                    "updated_at": record.updated_at.isoformat(),
                    "synced_at": record.synced_at.isoformat()
                    if record.synced_at
                    else None,
                }
            return None

        except Exception as e:
            self.logger.error(f"Error getting page sync record: {e}")
            return None

    def get_sync_record(
        self, content_hash: str, target_name: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get sync record for a specific content hash and target.

        Args:
            content_hash: Hash of the content
            target_name: Name of the target

        Returns:
            Sync record dict or None if not found
        """
        try:
            record = (
                self.db.query(SyncRecord)
                .filter(
                    and_(
                        SyncRecord.user_id == self.user_id,
                        SyncRecord.content_hash == content_hash,
                        SyncRecord.target_name == target_name,
                    )
                )
                .first()
            )

            if record:
                return {
                    "id": record.id,
                    "content_hash": record.content_hash,
                    "target_name": record.target_name,
                    "external_id": record.external_id,
                    "item_type": record.item_type,
                    "status": record.status,
                    "item_id": record.item_id,
                    "metadata": json.loads(record.metadata_json)
                    if record.metadata_json
                    else {},
                    "error_message": record.error_message,
                    "retry_count": record.retry_count,
                    "created_at": record.created_at.isoformat(),
                    "updated_at": record.updated_at.isoformat(),
                    "synced_at": record.synced_at.isoformat()
                    if record.synced_at
                    else None,
                }
            return None

        except Exception as e:
            self.logger.error(f"Error getting sync record: {e}")
            return None

    def record_sync_result(
        self,
        content_hash: str,
        target_name: str,
        item_id: str,
        item_type: SyncItemType,
        result: SyncResult,
        metadata: Optional[Dict] = None,
    ):
        """
        Record a sync result in the appropriate table.

        Args:
            content_hash: Hash of the synced content
            target_name: Name of the target system
            item_id: Local ID of the item
            item_type: Type of item synced
            result: Sync result
            metadata: Additional metadata to store
        """
        try:
            now = datetime.utcnow()
            synced_at = now if result.success else None

            # For PAGE_TEXT items, use page_sync_records table
            if item_type == SyncItemType.PAGE_TEXT:
                # Parse item_id to extract notebook_uuid and page_number
                parts = item_id.split(":page:")
                if len(parts) != 2:
                    self.logger.error(f"Invalid page item_id format: {item_id}")
                    return

                notebook_uuid = parts[0]
                page_number = int(parts[1])

                # Extract Notion IDs from result metadata
                notion_page_id = (
                    result.target_id
                    or result.metadata.get("notebook_page_id")
                    if result.metadata
                    else None
                )
                notion_block_id = (
                    result.metadata.get("page_block_id") if result.metadata else None
                )

                # Check if record exists
                existing = (
                    self.db.query(PageSyncRecord)
                    .filter(
                        and_(
                            PageSyncRecord.user_id == self.user_id,
                            PageSyncRecord.notebook_uuid == notebook_uuid,
                            PageSyncRecord.page_number == page_number,
                            PageSyncRecord.target_name == target_name,
                        )
                    )
                    .first()
                )

                if existing:
                    # Update existing
                    existing.content_hash = content_hash
                    existing.notion_page_id = notion_page_id
                    existing.notion_block_id = notion_block_id
                    existing.status = result.status.value
                    existing.error_message = result.error_message
                    existing.retry_count = 0  # Reset on new attempt
                    existing.updated_at = now
                    existing.synced_at = synced_at
                else:
                    # Create new
                    page_sync = PageSyncRecord(
                        user_id=self.user_id,
                        notebook_uuid=notebook_uuid,
                        page_number=page_number,
                        content_hash=content_hash,
                        target_name=target_name,
                        notion_page_id=notion_page_id,
                        notion_block_id=notion_block_id,
                        status=result.status.value,
                        error_message=result.error_message,
                        retry_count=0,
                        created_at=now,
                        updated_at=now,
                        synced_at=synced_at,
                    )
                    self.db.add(page_sync)

                self.logger.debug(
                    f"Recorded page sync result: {notebook_uuid} page {page_number} -> {target_name} = {result.status.value}"
                )

            else:
                # For non-page items, use sync_records table
                final_metadata = metadata or {}
                if result.metadata:
                    final_metadata.update(result.metadata)

                # Check if record exists
                existing = (
                    self.db.query(SyncRecord)
                    .filter(
                        and_(
                            SyncRecord.user_id == self.user_id,
                            SyncRecord.content_hash == content_hash,
                            SyncRecord.target_name == target_name,
                        )
                    )
                    .first()
                )

                if existing:
                    # Update existing
                    existing.external_id = result.target_id or ""
                    existing.item_type = item_type.value
                    existing.status = result.status.value
                    existing.item_id = item_id
                    existing.metadata_json = json.dumps(final_metadata)
                    existing.error_message = result.error_message
                    existing.retry_count = 0
                    existing.updated_at = now
                    existing.synced_at = synced_at
                else:
                    # Create new
                    sync_record = SyncRecord(
                        user_id=self.user_id,
                        content_hash=content_hash,
                        target_name=target_name,
                        external_id=result.target_id or "",
                        item_type=item_type.value,
                        status=result.status.value,
                        item_id=item_id,
                        metadata_json=json.dumps(final_metadata),
                        error_message=result.error_message,
                        retry_count=0,
                        created_at=now,
                        updated_at=now,
                        synced_at=synced_at,
                    )
                    self.db.add(sync_record)

                self.logger.debug(
                    f"Recorded sync result: {content_hash[:8]}... -> {target_name} = {result.status.value}"
                )

            self.db.commit()

        except Exception as e:
            self.logger.error(f"Error recording sync result: {e}")
            self.db.rollback()
            raise

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

    def get_specific_notebooks(
        self, target_name: str, notebook_uuids: List[str]
    ) -> List[SyncItem]:
        """
        Get specific notebooks by UUID for syncing.

        Args:
            target_name: Name of the target to check
            notebook_uuids: List of notebook UUIDs to sync

        Returns:
            List of SyncItems for the specified notebooks
        """
        try:
            # Get notebooks with matching UUIDs that have pages
            notebooks = (
                self.db.query(Notebook)
                .filter(
                    and_(
                        Notebook.user_id == self.user_id,
                        Notebook.deleted == False,
                        Notebook.notebook_uuid.in_(notebook_uuids),
                    )
                )
                .all()
            )

            sync_items = []

            for notebook in notebooks:
                # Get all pages for this notebook through the mapping table
                from app.models.notebook_page import NotebookPage
                notebook_pages = (
                    self.db.query(NotebookPage, Page)
                    .join(Page, NotebookPage.page_id == Page.id)
                    .filter(
                        and_(
                            NotebookPage.notebook_id == notebook.id,
                            Page.ocr_text.isnot(None)
                        )
                    )
                    .order_by(NotebookPage.page_number)
                    .all()
                )

                if not notebook_pages:
                    self.logger.warning(f"Notebook {notebook.notebook_uuid} has no pages with OCR text")
                    continue

                # Build page data (same format as get_notebooks_needing_sync)
                pages_data = [
                    {
                        "page_number": notebook_page.page_number,
                        "text": page.ocr_text or "",
                        "confidence": 0.8,  # Default confidence
                        "page_uuid": page.page_uuid or "",
                        "updated_at": page.updated_at.isoformat(),
                    }
                    for notebook_page, page in notebook_pages
                ]

                # Create text content for fingerprint
                text_content = "\n".join(
                    [
                        f"Page {page['page_number']}: {page['text']}"
                        for page in pages_data
                        if page.get("text", "").strip()
                    ]
                )

                # Build notebook data
                notebook_data = {
                    "notebook_uuid": notebook.notebook_uuid,
                    "notebook_name": notebook.visible_name or "Untitled Notebook",
                    "title": notebook.visible_name or "Untitled Notebook",
                    "pages": pages_data,
                    "full_path": notebook.full_path or "",
                }

                content_hash = ContentFingerprint.for_notebook(notebook_data)

                sync_item = SyncItem(
                    item_type=SyncItemType.NOTEBOOK,
                    item_id=notebook.notebook_uuid,
                    content_hash=content_hash,
                    data=notebook_data,
                    source_table="notebooks",
                    created_at=notebook.created_at,
                    updated_at=notebook.updated_at,
                )

                sync_items.append(sync_item)
                self.logger.info(f"Added notebook {notebook.visible_name} ({notebook.notebook_uuid}) with {len(pages)} pages to sync")

            return sync_items

        except Exception as e:
            self.logger.error(f"Error getting specific notebooks: {e}")
            return []

    def get_notebooks_needing_sync(
        self, target_name: str, limit: int = 100
    ) -> List[SyncItem]:
        """
        Get notebooks that need to be synced to a target.

        Args:
            target_name: Name of the target to check
            limit: Maximum number of items to return

        Returns:
            List of SyncItems for notebooks needing sync
        """
        try:
            # Get notebooks with pages
            notebooks = (
                self.db.query(Notebook)
                .join(Page, Notebook.id == Page.notebook_id)
                .filter(
                    and_(
                        Notebook.user_id == self.user_id,
                        Notebook.deleted == False,
                        Page.ocr_text.isnot(None),
                    )
                )
                .distinct()
                .limit(limit)
                .all()
            )

            sync_items = []

            for notebook in notebooks:
                # Get all pages for this notebook
                from app.models.notebook_page import NotebookPage
                notebook_pages = (
                    self.db.query(NotebookPage, Page)
                    .join(Page, NotebookPage.page_id == Page.id)
                    .filter(
                        and_(
                            NotebookPage.notebook_id == notebook.id,
                            Page.ocr_text.isnot(None)
                        )
                    )
                    .order_by(NotebookPage.page_number)
                    .all()
                )

                if not notebook_pages:
                    continue

                # Build page data
                pages_data = [
                    {
                        "page_number": notebook_page.page_number,
                        "text": page.ocr_text or "",
                        "confidence": 0.8,  # Default confidence
                        "page_uuid": page.page_uuid or "",
                        "updated_at": page.updated_at.isoformat(),
                    }
                    for notebook_page, page in notebook_pages
                ]

                # Create text content for fingerprint
                text_content = "\n".join(
                    [
                        f"Page {page['page_number']}: {page['text']}"
                        for page in pages_data
                        if page.get("text", "").strip()
                    ]
                )

                # Build notebook data
                notebook_data = {
                    "notebook_uuid": notebook.notebook_uuid,
                    "notebook_name": notebook.visible_name or "Untitled Notebook",
                    "title": notebook.visible_name or "Untitled Notebook",
                    "pages": pages_data,
                    "text_content": text_content,
                    "page_count": len(pages_data),
                    "type": "notebook",
                    "full_path": notebook.full_path,
                    "created_at": notebook.created_at.isoformat(),
                    "updated_at": notebook.updated_at.isoformat(),
                }

                # Generate content hash
                content_hash = ContentFingerprint.for_notebook(notebook_data)

                # Check if already synced
                existing_sync = self.get_sync_record(content_hash, target_name)
                if (
                    existing_sync
                    and existing_sync["status"] == SyncStatus.SUCCESS.value
                ):
                    continue  # Skip already synced notebooks

                # Create sync item
                sync_item = SyncItem(
                    item_type=SyncItemType.NOTEBOOK,
                    item_id=notebook.notebook_uuid,
                    content_hash=content_hash,
                    data=notebook_data,
                    source_table="notebooks",
                    created_at=notebook.created_at,
                    updated_at=notebook.updated_at,
                )

                sync_items.append(sync_item)

            return sync_items

        except Exception as e:
            self.logger.error(f"Error getting notebooks needing sync: {e}")
            return []
