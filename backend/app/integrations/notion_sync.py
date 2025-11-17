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

    def __init__(self, api_token: str, database_id: str, verify_ssl: bool = False):
        """
        Initialize Notion sync target.

        Args:
            api_token: Notion integration API token
            database_id: Notion database ID to sync to
            verify_ssl: Whether to verify SSL certificates (False for corporate environments)
        """
        super().__init__("notion")
        self.api_token = api_token
        self.database_id = database_id

        # Create httpx client with SSL verification control
        if verify_ssl:
            self.client = NotionClient(auth=api_token)
        else:
            # Disable SSL verification for corporate environments
            self.logger.warning("⚠️ SSL verification disabled for Notion API calls")
            http_client = httpx.Client(verify=False)
            self.client = NotionClient(auth=api_token, client=http_client)

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
                    metadata={"reason": "Todo sync not yet implemented"},
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

            # Check if page already exists
            existing_page_id = await self.find_existing_page(notebook_uuid)

            if existing_page_id:
                # Update existing page
                success = await self._update_notion_page(
                    existing_page_id, title, pages, full_path
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
                    notebook_uuid, title, pages, full_path
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
        """Sync individual page text as a block to existing Notion page."""
        return SyncResult(
            status=SyncStatus.SKIPPED,
            metadata={"reason": "Page-level sync not yet implemented"},
        )

    async def find_existing_page(self, notebook_uuid: str) -> Optional[str]:
        """
        Find existing Notion page for a notebook UUID.

        Args:
            notebook_uuid: Notebook UUID to search for

        Returns:
            Notion page ID if found, None otherwise
        """
        try:
            # Query database for pages with matching UUID
            response = self.client.databases.query(
                database_id=self.database_id,
                filter={
                    "property": "UUID",
                    "rich_text": {"equals": notebook_uuid},
                }
            )

            results = response.get("results", [])
            if results:
                return results[0]["id"]
            return None

        except Exception as e:
            self.logger.error(f"Error finding existing Notion page: {e}")
            return None

    async def _create_notion_page(
        self, notebook_uuid: str, title: str, pages: List[Dict], full_path: str
    ) -> Optional[str]:
        """
        Create a new page in Notion database.

        Args:
            notebook_uuid: UUID of the notebook
            title: Title of the notebook
            pages: List of page data
            full_path: Full folder path

        Returns:
            Notion page ID if successful, None otherwise
        """
        try:
            # Build page properties
            properties = {
                "Name": {"title": [{"text": {"content": title}}]},
                "UUID": {"rich_text": [{"text": {"content": notebook_uuid}}]},
                "Path": {"rich_text": [{"text": {"content": full_path or ""}}]},
                "Pages": {"number": len(pages)},
            }

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
        self, page_id: str, title: str, pages: List[Dict], full_path: str
    ) -> bool:
        """
        Update an existing Notion page.

        Args:
            page_id: Notion page ID
            title: Updated title
            pages: Updated page data
            full_path: Updated folder path

        Returns:
            True if successful, False otherwise
        """
        try:
            # Update properties
            properties = {
                "Name": {"title": [{"text": {"content": title}}]},
                "Path": {"rich_text": [{"text": {"content": full_path or ""}}]},
                "Pages": {"number": len(pages)},
            }

            self.client.pages.update(page_id=page_id, properties=properties)

            # TODO: Update page content blocks
            # For now, we'll just update properties

            self.logger.info(f"Updated Notion page: {page_id}")
            return True

        except Exception as e:
            self.logger.error(f"Error updating Notion page: {e}")
            return False

    def _build_page_blocks(self, pages: List[Dict]) -> List[Dict]:
        """
        Build Notion blocks from page data.

        Args:
            pages: List of page dictionaries with text content

        Returns:
            List of Notion block objects
        """
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

        # Add each page as a toggle block
        for page in pages[:20]:  # Limit to 20 pages to avoid API limits
            page_number = page.get("page_number", 0)
            text = page.get("text", "")

            if not text.strip():
                continue

            # Create toggle block for the page
            page_block = {
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
                    "todos": False,
                    "highlights": False,
                    "page_text": False,
                },
            }
        except Exception as e:
            return {
                "target_name": self.target_name,
                "connected": False,
                "error": str(e),
            }
