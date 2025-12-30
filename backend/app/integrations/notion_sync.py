"""Notion sync target implementation for rmirror Cloud."""

import logging
from typing import Any, Dict, List, Optional

import httpx
from notion_client import Client as NotionClient

from app.core.sync_engine import SyncItem, SyncResult, SyncTarget
from app.integrations.notion_markdown import MarkdownToNotionConverter
from app.models.sync_record import SyncItemType, SyncStatus

logger = logging.getLogger(__name__)


class NotionSyncTarget(SyncTarget):
    """
    Notion implementation of the sync target interface.

    This handles syncing notebooks and pages to a Notion database.
    """

    def __init__(self, access_token: str, database_id: str, verify_ssl: bool = False):
        """
        Initialize Notion sync target.

        Args:
            access_token: Notion OAuth access token or integration API token
            database_id: Notion database ID for notebooks
            verify_ssl: Whether to verify SSL certificates (False for corporate environments)
        """
        super().__init__("notion")
        self.access_token = access_token
        self.database_id = database_id

        # Create httpx client with SSL verification control
        if verify_ssl:
            self.client = NotionClient(
                auth=access_token,
                notion_version="2025-09-03"  # Use new API version
            )
        else:
            # Disable SSL verification for corporate environments
            self.logger.warning("⚠️ SSL verification disabled for Notion API calls")
            http_client = httpx.Client(verify=False)
            self.client = NotionClient(
                auth=access_token,
                client=http_client,
                notion_version="2025-09-03"  # Use new API version
            )

        self.markdown_converter = MarkdownToNotionConverter()
        self.logger.info(f"Initialized Notion sync target with database {database_id}")

    async def sync_item(self, item: SyncItem) -> SyncResult:
        """Sync a single item to Notion."""
        try:
            if item.item_type == SyncItemType.NOTEBOOK:
                return await self._sync_notebook(item)
            elif item.item_type == SyncItemType.PAGE_TEXT:
                return await self._sync_page_text(item)
            elif item.item_type == SyncItemType.TODO:
                return SyncResult(
                    status=SyncStatus.SKIPPED,
                    metadata={"reason": "Todos should use notion-todos integration"},
                )
            elif item.item_type == SyncItemType.HIGHLIGHT:
                return SyncResult(
                    status=SyncStatus.SKIPPED,
                    metadata={"reason": "Highlights handled via notebook sync"},
                )
            else:
                return SyncResult(
                    status=SyncStatus.FAILED,
                    error_message=f"Unsupported item type: {item.item_type}",
                )
        except Exception as e:
            self.logger.error(f"Error syncing {item.item_type} to Notion: {e}")
            return SyncResult(status=SyncStatus.FAILED, error_message=str(e))

    async def _sync_notebook(self, item: SyncItem) -> SyncResult:
        """Sync a notebook to Notion as a page in the database."""
        try:
            notebook_data = item.data
            notebook_uuid = notebook_data.get("notebook_uuid")
            title = notebook_data.get("title", "Untitled Notebook")
            full_path = notebook_data.get("full_path", "")
            pages = notebook_data.get("pages", [])
            last_opened = notebook_data.get("last_opened_at")  # reMarkable lastOpened timestamp
            last_modified = notebook_data.get("last_modified_at")  # reMarkable lastModified timestamp

            # Check if page already exists
            existing_page_id = await self.find_existing_page(notebook_uuid)

            if existing_page_id:
                # Update existing page
                success = await self._update_notion_page(
                    existing_page_id, notebook_uuid, title, pages, full_path,
                    last_opened, last_modified
                )
                if success:
                    return SyncResult(
                        status=SyncStatus.SUCCESS,
                        target_id=existing_page_id,
                        metadata={"action": "updated"},
                    )
                else:
                    return SyncResult(
                        status=SyncStatus.RETRY,
                        error_message="Failed to update existing Notion page",
                    )
            else:
                # Create new page
                page_id = await self._create_notion_page(
                    notebook_uuid, title, pages, full_path,
                    last_opened, last_modified
                )
                if page_id:
                    return SyncResult(
                        status=SyncStatus.SUCCESS,
                        target_id=page_id,
                        metadata={"action": "created"},
                    )
                else:
                    return SyncResult(
                        status=SyncStatus.RETRY,
                        error_message="Failed to create Notion page",
                    )

        except Exception as e:
            self.logger.error(f"Error syncing notebook to Notion: {e}")
            return SyncResult(status=SyncStatus.FAILED, error_message=str(e))

    async def _sync_page_text(self, item: SyncItem) -> SyncResult:
        """
        Sync individual page text to Notion using database-tracked block IDs.

        The worker passes existing_block_id if this page was previously synced.
        If block ID exists, we update the existing block.
        If no block ID, we create a new one in the correct position.
        """
        try:
            page_data = item.data
            page_text = page_data.get("text", "")
            page_number = page_data.get("page_number")
            notebook_uuid = page_data.get("notebook_uuid")
            existing_block_id = page_data.get("existing_block_id")  # From SyncRecord

            if not page_text.strip():
                return SyncResult(
                    status=SyncStatus.SKIPPED,
                    metadata={"reason": "Empty page content"},
                )

            if page_number is None:
                return SyncResult(
                    status=SyncStatus.FAILED,
                    error_message="Missing page_number in sync item data",
                )

            # Find the parent Notion page for this notebook
            parent_page_id = await self.find_existing_page(notebook_uuid)

            if not parent_page_id:
                # Auto-create the notebook page if it doesn't exist
                notebook_name = page_data.get("notebook_name", "Untitled Notebook")
                self.logger.info(f"Creating parent notebook page for {notebook_name} ({notebook_uuid})")

                parent_page_id = await self._create_notion_page(
                    notebook_uuid=notebook_uuid,
                    title=notebook_name,
                    pages=[],  # Empty pages list, will be updated later
                    full_path="",  # Don't have folder path from page data
                )

                if not parent_page_id:
                    return SyncResult(
                        status=SyncStatus.FAILED,
                        error_message=f"Failed to create parent notebook page for {notebook_uuid}",
                    )

            # Convert text to Notion blocks
            blocks = self._text_to_blocks(page_text, max_blocks=50)

            if not blocks:
                return SyncResult(
                    status=SyncStatus.SKIPPED,
                    metadata={"reason": "No blocks generated from content"},
                )

            # Create clean toggle block WITHOUT hash
            page_toggle = {
                "object": "block",
                "type": "toggle",
                "toggle": {
                    "rich_text": [
                        {
                            "type": "text",
                            "text": {"content": f"📄 Page {page_number}"},
                            "annotations": {"bold": True},
                        }
                    ],
                    "children": blocks,
                },
            }

            if existing_block_id:
                # Page was previously synced - update by deleting old and creating new
                self.logger.info(f"Updating existing page {page_number} (block {existing_block_id})")

                block_deleted = False
                try:
                    # Try to delete old block
                    self.client.blocks.delete(block_id=existing_block_id)
                    block_deleted = True
                except Exception as e:
                    error_msg = str(e)
                    # Check if block is archived or doesn't exist
                    if "archived" in error_msg.lower() or "not found" in error_msg.lower() or "Could not find block" in error_msg:
                        self.logger.info(f"Block {existing_block_id} is archived/deleted, will create fresh block")
                        # Block is gone/archived, treat as new page
                        block_deleted = True  # Pretend it was deleted since it's effectively gone
                    else:
                        self.logger.warning(f"Failed to delete old block {existing_block_id}: {e}")

                # Create new block (will go to end for updates, but that's okay)
                response = self.client.blocks.children.append(
                    block_id=parent_page_id,
                    children=[page_toggle]
                )

                new_block_id = response["results"][0]["id"] if response.get("results") else None

                return SyncResult(
                    status=SyncStatus.SUCCESS,
                    target_id=new_block_id or parent_page_id,
                    metadata={
                        "action": "page_updated" if block_deleted else "page_recreated",
                        "page_number": page_number,
                        "parent_page_id": parent_page_id,
                    }
                )
            else:
                # New page - insert in correct position (reverse order)
                self.logger.info(f"Creating new page {page_number}")

                # Get all blocks to find insertion point
                all_blocks = []
                start_cursor = None
                while True:
                    if start_cursor:
                        response = self.client.blocks.children.list(
                            block_id=parent_page_id,
                            start_cursor=start_cursor
                        )
                    else:
                        response = self.client.blocks.children.list(block_id=parent_page_id)

                    all_blocks.extend(response.get("results", []))

                    if not response.get("has_more", False):
                        break
                    start_cursor = response.get("next_cursor")

                # Find insertion point for reverse order (highest page first)
                insert_after_block_id = None

                # First, find heading block
                import re
                for block in all_blocks:
                    if block.get("type") == "heading_2":
                        insert_after_block_id = block["id"]
                        break

                # Then find first page with HIGHER number
                for block in all_blocks:
                    if block.get("type") == "toggle":
                        toggle_data = block.get("toggle", {})
                        rich_text = toggle_data.get("rich_text", [])
                        if rich_text:
                            content = rich_text[0].get("text", {}).get("content", "")
                            match = re.match(r"📄 Page (\d+)", content)
                            if match:
                                block_page_num = int(match.group(1))
                                if block_page_num > page_number:
                                    insert_after_block_id = block["id"]
                                elif block_page_num < page_number:
                                    break

                # Insert the new page
                if insert_after_block_id:
                    response = self.client.blocks.children.append(
                        block_id=parent_page_id,
                        children=[page_toggle],
                        after=insert_after_block_id
                    )
                else:
                    response = self.client.blocks.children.append(
                        block_id=parent_page_id,
                        children=[page_toggle]
                    )

                new_block_id = response["results"][0]["id"] if response.get("results") else None

                return SyncResult(
                    status=SyncStatus.SUCCESS,
                    target_id=new_block_id or parent_page_id,
                    metadata={
                        "action": "page_created",
                        "page_number": page_number,
                        "parent_page_id": parent_page_id,
                    }
                )

        except Exception as e:
            self.logger.error(f"Error syncing page text: {e}")
            return SyncResult(status=SyncStatus.FAILED, error_message=str(e))

    async def _sync_page_text_OLD_DELETE_ME(self, item: SyncItem) -> SyncResult:
        """OLD VERSION - DELETE THIS"""
        try:
            if existing_page_block and not content_changed:
                # Page already exists with same content, skip
                self.logger.info(f"Page {page_number} already exists with same content, skipping")
                return SyncResult(
                    status=SyncStatus.SKIPPED,
                    metadata={
                        "reason": "page_unchanged",
                        "page_number": page_number,
                        "parent_page_id": parent_page_id,
                    }
                )
            elif existing_page_block and content_changed:
                # Page exists but content changed, delete old block and add new one in same position
                self.logger.info(f"Page {page_number} changed (hash: {existing_hash} → {current_hash}), replacing")

                # Find the block that comes BEFORE the existing page (to use as 'after' anchor)
                insert_after_block_id = None
                found_existing = False
                for i, block in enumerate(all_blocks):
                    if block["id"] == existing_page_block["id"]:
                        found_existing = True
                        # Get the previous block (the one before this page)
                        if i > 0:
                            insert_after_block_id = all_blocks[i - 1]["id"]
                        break

                # Delete the old block
                try:
                    self.client.blocks.delete(block_id=existing_page_block["id"])
                except Exception as e:
                    self.logger.warning(f"Failed to delete old block for page {page_number}: {e}")

                # Add new block in the same position using 'after' parameter
                if insert_after_block_id:
                    response = self.client.blocks.children.append(
                        block_id=parent_page_id,
                        children=[page_toggle],
                        after=insert_after_block_id
                    )
                    self.logger.info(f"Replaced page {page_number} after block {insert_after_block_id}")
                else:
                    # No previous block, add at the beginning (after parent)
                    response = self.client.blocks.children.append(
                        block_id=parent_page_id,
                        children=[page_toggle]
                    )
                    self.logger.info(f"Replaced page {page_number} at beginning")

                block_id = response["results"][0]["id"] if response.get("results") else None

                return SyncResult(
                    status=SyncStatus.SUCCESS,
                    target_id=block_id or parent_page_id,
                    metadata={
                        "action": "page_replaced",
                        "page_number": page_number,
                        "blocks_added": len(blocks),
                        "parent_page_id": parent_page_id,
                    }
                )
            else:
                # New page - insert it in correct position using the 'after' parameter
                # Find the insertion anchor: the block that should come BEFORE this page
                # In reverse order, higher page numbers come first
                self.logger.info(f"Adding new page {page_number} to Notion in correct position")

                insert_after_block_id = None

                # First, look for the heading block - new highest page should go after heading
                for block in all_blocks:
                    if block.get("type") == "heading_2":
                        insert_after_block_id = block["id"]
                        break

                # Then find the first existing page with a HIGHER number than ours
                # We want to insert after that page (to maintain descending order)
                for block in all_blocks:
                    if block.get("type") == "toggle":
                        toggle_data = block.get("toggle", {})
                        rich_text = toggle_data.get("rich_text", [])
                        if rich_text:
                            content = rich_text[0].get("text", {}).get("content", "")
                            match = re.match(r"📄 Page (\d+)(?: \[([a-f0-9]+)\])?", content)
                            if match:
                                block_page_num = int(match.group(1))
                                # If this existing page has a higher number, insert after it
                                if block_page_num > page_number:
                                    insert_after_block_id = block["id"]
                                # Once we hit a lower number, stop searching
                                elif block_page_num < page_number:
                                    break

                # Insert the new page using the 'after' parameter
                if insert_after_block_id:
                    response = self.client.blocks.children.append(
                        block_id=parent_page_id,
                        children=[page_toggle],
                        after=insert_after_block_id
                    )
                    self.logger.info(f"Inserted page {page_number} after block {insert_after_block_id}")
                else:
                    # No anchor found, append to end (shouldn't normally happen)
                    response = self.client.blocks.children.append(
                        block_id=parent_page_id,
                        children=[page_toggle]
                    )
                    self.logger.info(f"Appended page {page_number} to end (no anchor found)")

                block_id = response["results"][0]["id"] if response.get("results") else None

                return SyncResult(
                    status=SyncStatus.SUCCESS,
                    target_id=block_id or parent_page_id,
                    metadata={
                        "action": "page_added",
                        "page_number": page_number,
                        "blocks_added": len(blocks),
                        "parent_page_id": parent_page_id,
                        "insert_after_block_id": insert_after_block_id,
                    }
                )

        except Exception as e:
            self.logger.error(f"Error syncing page text: {e}")
            return SyncResult(status=SyncStatus.FAILED, error_message=str(e))

    def _extract_tags_from_path(self, full_path: str) -> List[str]:
        """
        Extract tags from folder path.

        Example: "Work/Projects/Client A" → ["Work", "Projects", "Client A"]

        Args:
            full_path: Full folder path with "/" separators

        Returns:
            List of tags (folder names)
        """
        if not full_path or full_path == "/":
            return []

        # Remove leading/trailing slashes and split
        path_parts = full_path.strip("/").split("/")

        # Filter out empty parts
        return [part for part in path_parts if part.strip()]

    async def find_existing_page(self, notebook_uuid: str) -> Optional[str]:
        """
        Find existing Notion page for a notebook UUID.

        Args:
            notebook_uuid: Notebook UUID to search for

        Returns:
            Notion page ID if found, None otherwise
        """
        try:
            # Search for pages in the database that contain the UUID in the title
            # Since we store the UUID as part of the title like "Name [uuid]"
            uuid_prefix = notebook_uuid[:8]

            # Use search API to find pages
            response = self.client.search(
                query=uuid_prefix,
                filter={"property": "object", "value": "page"}
            )

            # Filter results to only those in our database
            for result in response.get("results", []):
                if result.get("parent", {}).get("database_id") == self.database_id:
                    # Check if the title contains our UUID
                    title_prop = result.get("properties", {}).get("Name", {})
                    title_content = title_prop.get("title", [])
                    if title_content:
                        title_text = title_content[0].get("text", {}).get("content", "")
                        if uuid_prefix in title_text:
                            return result["id"]

            return None

        except Exception as e:
            self.logger.error(f"Error finding existing Notion page: {e}")
            return None

    async def _create_notion_page(
        self, notebook_uuid: str, title: str, pages: List[Dict], full_path: str,
        last_opened: Optional[str] = None, last_modified: Optional[str] = None
    ) -> Optional[str]:
        """
        Create a new page in Notion database.

        Args:
            notebook_uuid: UUID of the notebook
            title: Title of the notebook
            pages: List of page data
            full_path: Full folder path
            last_opened: When notebook was last opened on reMarkable (ISO 8601)
            last_modified: When notebook was last modified on reMarkable (ISO 8601)

        Returns:
            Notion page ID if successful, None otherwise
        """
        try:
            from datetime import datetime

            # Build page properties with all metadata
            properties = {
                "Name": {"title": [{"text": {"content": f"{title} [{notebook_uuid[:8]}]"}}]},
                "UUID": {"rich_text": [{"text": {"content": notebook_uuid}}]},
                "Path": {"rich_text": [{"text": {"content": full_path or ""}}]},
                "Pages": {"number": len(pages)},
            }

            # Add Tags from path
            tags = self._extract_tags_from_path(full_path)
            if tags:
                properties["Tags"] = {"multi_select": [{"name": tag} for tag in tags]}

            # Add Last Opened if available
            if last_opened:
                try:
                    properties["Last Opened"] = {"date": {"start": last_opened}}
                except Exception as e:
                    self.logger.warning(f"Invalid last_opened format: {last_opened}, error: {e}")

            # Add Last Modified if available
            if last_modified:
                try:
                    properties["Last Modified"] = {"date": {"start": last_modified}}
                except Exception as e:
                    self.logger.warning(f"Invalid last_modified format: {last_modified}, error: {e}")

            # Add Synced At timestamp
            properties["Synced At"] = {"date": {"start": datetime.utcnow().isoformat()}}

            # Add Status
            properties["Status"] = {"select": {"name": "Synced"}}

            # Build page content from pages
            children = self._build_page_blocks(pages)

            # Create the page
            response = self.client.pages.create(
                parent={"database_id": self.database_id},
                properties=properties,
                children=children[:100],  # Notion limit is 100 blocks per request
            )

            page_id = response["id"]
            self.logger.info(f"Created Notion page: {page_id} for notebook {title}")
            return page_id

        except Exception as e:
            self.logger.error(f"Error creating Notion page: {e}")
            return None

    async def _update_notion_page(
        self, page_id: str, notebook_uuid: str, title: str, pages: List[Dict], full_path: str,
        last_opened: Optional[str] = None, last_modified: Optional[str] = None
    ) -> bool:
        """
        Update an existing Notion page with granular page-level deduplication.

        Args:
            page_id: Notion page ID
            notebook_uuid: UUID of the notebook
            title: Updated title
            pages: Updated page data
            full_path: Updated folder path
            last_opened: When notebook was last opened on reMarkable (ISO 8601)
            last_modified: When notebook was last modified on reMarkable (ISO 8601)

        Returns:
            True if successful, False otherwise
        """
        try:
            from datetime import datetime
            import hashlib
            import json
            import re

            # Update properties with all metadata
            properties = {
                "Name": {"title": [{"text": {"content": f"{title} [{notebook_uuid[:8]}]"}}]},
                "UUID": {"rich_text": [{"text": {"content": notebook_uuid}}]},
                "Path": {"rich_text": [{"text": {"content": full_path or ""}}]},
                "Pages": {"number": len(pages)},
                "Synced At": {"date": {"start": datetime.utcnow().isoformat()}},
                "Status": {"select": {"name": "Synced"}},
            }

            # Update Tags from path
            tags = self._extract_tags_from_path(full_path)
            if tags:
                properties["Tags"] = {"multi_select": [{"name": tag} for tag in tags]}
            else:
                # Clear tags if path is empty
                properties["Tags"] = {"multi_select": []}

            # Update Last Opened if available
            if last_opened:
                try:
                    properties["Last Opened"] = {"date": {"start": last_opened}}
                except Exception as e:
                    self.logger.warning(f"Invalid last_opened format: {last_opened}, error: {e}")

            # Update Last Modified if available
            if last_modified:
                try:
                    properties["Last Modified"] = {"date": {"start": last_modified}}
                except Exception as e:
                    self.logger.warning(f"Invalid last_modified format: {last_modified}, error: {e}")

            # Always update properties (metadata may have changed even if content didn't)
            self.client.pages.update(page_id=page_id, properties=properties)

            # Get existing blocks to compare page-by-page
            existing_blocks = self.client.blocks.children.list(block_id=page_id)
            existing_page_blocks = {}  # Map of page_number -> (block_id, hash)

            # Parse existing page blocks to extract page numbers and hashes
            for block in existing_blocks.get("results", []):
                if block.get("type") == "toggle":
                    toggle_data = block.get("toggle", {})
                    rich_text = toggle_data.get("rich_text", [])
                    if rich_text:
                        content = rich_text[0].get("text", {}).get("content", "")
                        # Parse format: "📄 Page 1 [abc12345]"
                        match = re.match(r"📄 Page (\d+) \[([a-f0-9]+)\]", content)
                        if match:
                            page_num = int(match.group(1))
                            page_hash = match.group(2)
                            existing_page_blocks[page_num] = (block["id"], page_hash)

            # Calculate hashes for current pages
            current_page_hashes = {}  # Map of page_number -> hash
            for page in pages[:20]:
                page_number = page.get("page_number", 0)
                text = page.get("text", "")
                if not text.strip():
                    continue

                page_hash_data = json.dumps({
                    "page_number": page_number,
                    "text": text
                }, sort_keys=True)
                page_hash = hashlib.sha256(page_hash_data.encode()).hexdigest()[:8]
                current_page_hashes[page_number] = page_hash

            # Determine which pages need updating
            pages_to_delete = []
            pages_to_add = []

            # Check which existing pages have changed or been removed
            for page_num, (block_id, old_hash) in existing_page_blocks.items():
                if page_num not in current_page_hashes:
                    # Page was removed
                    pages_to_delete.append(block_id)
                    self.logger.info(f"Page {page_num} removed, will delete block")
                elif current_page_hashes[page_num] != old_hash:
                    # Page content changed
                    pages_to_delete.append(block_id)
                    self.logger.info(f"Page {page_num} changed (hash: {old_hash} → {current_page_hashes[page_num]})")

            # Check which pages are new or need to be recreated
            for page in pages[:20]:
                page_number = page.get("page_number", 0)
                text = page.get("text", "")
                if not text.strip():
                    continue

                current_hash = current_page_hashes.get(page_number)
                if page_number not in existing_page_blocks:
                    # New page
                    pages_to_add.append(page)
                    self.logger.info(f"Page {page_number} is new, will add")
                elif existing_page_blocks[page_number][1] != current_hash:
                    # Changed page (already marked for deletion above)
                    pages_to_add.append(page)

            # Delete changed/removed page blocks
            if pages_to_delete:
                self.logger.info(f"Deleting {len(pages_to_delete)} changed/removed page blocks...")
                for block_id in pages_to_delete:
                    try:
                        self.client.blocks.delete(block_id=block_id)
                    except Exception as e:
                        self.logger.warning(f"Failed to delete block {block_id}: {e}")

            # Add new/changed page blocks
            if pages_to_add:
                self.logger.info(f"Adding {len(pages_to_add)} new/changed page blocks...")

                # Sort pages in reverse order (highest page number first) for most recent first
                pages_to_add_sorted = sorted(pages_to_add, key=lambda p: p.get("page_number", 0), reverse=True)

                # Build blocks for the pages that need adding
                new_blocks = []
                for page in pages_to_add_sorted:
                    page_number = page.get("page_number", 0)
                    text = page.get("text", "")

                    # Calculate hash
                    page_hash_data = json.dumps({
                        "page_number": page_number,
                        "text": text
                    }, sort_keys=True)
                    page_hash = hashlib.sha256(page_hash_data.encode()).hexdigest()[:8]

                    # Create toggle block with hash
                    page_block = {
                        "object": "block",
                        "type": "toggle",
                        "toggle": {
                            "rich_text": [
                                {
                                    "type": "text",
                                    "text": {"content": f"📄 Page {page_number} [{page_hash}]"},
                                    "annotations": {"bold": True},
                                }
                            ],
                            "children": self._text_to_blocks(text),
                        },
                    }
                    new_blocks.append(page_block)

                # Add blocks in batches of 100 (Notion limit)
                for i in range(0, len(new_blocks), 100):
                    batch = new_blocks[i:i+100]
                    self.client.blocks.children.append(
                        block_id=page_id,
                        children=batch
                    )

            if pages_to_delete or pages_to_add:
                self.logger.info(f"Updated Notion page: deleted {len(pages_to_delete)} blocks, added {len(pages_to_add)} pages")
            else:
                self.logger.info(f"No page-level changes for {title}, skipped block updates")

            return True

        except Exception as e:
            self.logger.error(f"Error updating Notion page: {e}")
            return False

    def _build_page_blocks(self, pages: List[Dict]) -> List[Dict]:
        """
        Build Notion blocks from page data with content hashes for deduplication.

        Pages are ordered in reverse (highest page number first) so the most recent
        content appears at the top of the Notion page.

        Args:
            pages: List of page dictionaries with text content

        Returns:
            List of Notion block objects with embedded page hashes, ordered by page number descending
        """
        import hashlib
        import json

        blocks = []

        # Add a heading for the notebook content
        blocks.append(
            {
                "object": "block",
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [
                        {"type": "text", "text": {"content": "Notebook Content"}}
                    ]
                },
            }
        )

        # Filter pages with content and sort in reverse order (highest page number first)
        pages_with_content = [p for p in pages[:20] if p.get("text", "").strip()]
        pages_sorted = sorted(pages_with_content, key=lambda p: p.get("page_number", 0), reverse=True)

        # Add each page as a toggle block with embedded hash
        for page in pages_sorted:
            page_number = page.get("page_number", 0)
            text = page.get("text", "")

            # Calculate hash for this specific page
            page_hash_data = json.dumps({
                "page_number": page_number,
                "text": text
            }, sort_keys=True)
            page_hash = hashlib.sha256(page_hash_data.encode()).hexdigest()[:8]

            # Create toggle block for the page with hash embedded in title
            # Format: "📄 Page 1 [abc12345]" where abc12345 is the hash
            page_block = {
                "object": "block",
                "type": "toggle",
                "toggle": {
                    "rich_text": [
                        {
                            "type": "text",
                            "text": {"content": f"📄 Page {page_number} [{page_hash}]"},
                            "annotations": {"bold": True},
                        }
                    ],
                    "children": self._text_to_blocks(text),
                },
            }

            blocks.append(page_block)

        return blocks

    def _text_to_blocks(self, text: str, max_blocks: int = 100) -> List[Dict]:
        """
        Convert text with markdown to Notion blocks.

        Args:
            text: Text content to convert (may contain markdown)
            max_blocks: Maximum number of blocks to create

        Returns:
            List of Notion blocks with proper formatting
        """
        # Use the markdown converter to properly format text
        return self.markdown_converter.text_to_notion_blocks(text, max_blocks)

    async def check_duplicate(self, content_hash: str) -> Optional[str]:
        """Check if content with this hash already exists in Notion."""
        # For Notion, we use the notebook UUID as the primary identifier
        # Content hash checking is handled by the sync manager
        return None

    async def update_item(self, external_id: str, item: SyncItem) -> SyncResult:
        """Update an existing item in Notion."""
        try:
            if item.item_type == SyncItemType.NOTEBOOK:
                notebook_data = item.data
                title = notebook_data.get("title", "Untitled")
                pages = notebook_data.get("pages", [])
                full_path = notebook_data.get("full_path", "")

                success = await self._update_notion_page(
                    external_id, title, pages, full_path
                )
                if success:
                    return SyncResult(
                        status=SyncStatus.SUCCESS,
                        target_id=external_id,
                        metadata={"action": "updated"},
                    )
                else:
                    return SyncResult(
                        status=SyncStatus.RETRY,
                        error_message="Failed to update Notion page",
                    )
            else:
                return SyncResult(
                    status=SyncStatus.FAILED,
                    error_message=f"Update not supported for {item.item_type}",
                )
        except Exception as e:
            return SyncResult(status=SyncStatus.FAILED, error_message=str(e))

    async def delete_item(self, external_id: str) -> SyncResult:
        """Delete (archive) an item from Notion."""
        try:
            # Notion doesn't really support deletion, but we can archive
            self.client.pages.update(page_id=external_id, archived=True)
            return SyncResult(
                status=SyncStatus.SUCCESS,
                metadata={
                    "action": "archived",
                    "note": "Notion pages archived, not deleted",
                },
            )
        except Exception as e:
            return SyncResult(status=SyncStatus.FAILED, error_message=str(e))

    async def validate_connection(self) -> bool:
        """
        Validate connection to Notion.

        Returns:
            True if connection is valid, False otherwise
        """
        try:
            # Test connection by querying the database
            self.client.databases.retrieve(database_id=self.database_id)
            return True
        except Exception as e:
            self.logger.error(f"Failed to validate Notion connection: {e}")
            return False

    def get_target_info(self) -> Dict[str, Any]:
        """Get information about this Notion target."""
        try:
            # Test connection by querying the database
            response = self.client.databases.retrieve(database_id=self.database_id)

            return {
                "target_name": self.target_name,
                "connected": True,
                "database_id": self.database_id,
                "database_title": response.get("title", [{}])[0]
                .get("text", {})
                .get("content", "Unknown"),
                "capabilities": {
                    "notebooks": True,
                    "highlights": False,
                    "page_text": True,
                },
            }
        except Exception as e:
            return {
                "target_name": self.target_name,
                "connected": False,
                "error": str(e),
            }
