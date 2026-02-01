"""Notion Todos sync target implementation for rmirror Cloud."""

import logging
from datetime import datetime
from typing import Any, Dict, Optional

import httpx
from notion_client import Client as NotionClient

from app.core.sync_engine import SyncItem, SyncResult, SyncTarget
from app.models.sync_record import SyncItemType, SyncStatus

logger = logging.getLogger(__name__)


class NotionTodosSyncTarget(SyncTarget):
    """
    Notion implementation for syncing todos to a dedicated database.

    This integration syncs todos as separate pages in a Notion database,
    making them proper tasks that can be managed independently from notebooks.

    Supports adaptive property usage:
    - For newly created databases: uses Workflow (select type)
    - For existing databases with Status (status type): uses Status
    """

    def __init__(
        self,
        access_token: str,
        database_id: str,
        verify_ssl: bool = False,
        use_status_property: bool = False,
    ):
        """
        Initialize Notion todos sync target.

        Args:
            access_token: Notion OAuth access token or integration API token
            database_id: Notion database ID for todos
            verify_ssl: Whether to verify SSL certificates (False for corporate environments)
            use_status_property: If True, use Status (status type) instead of Workflow (select)
                               This is True for existing databases with Status property
        """
        super().__init__("notion-todos")
        self.access_token = access_token
        self.database_id = database_id
        self.use_status_property = use_status_property

        # Create httpx client with SSL verification control
        if verify_ssl:
            self.client = NotionClient(auth=access_token)
        else:
            # Disable SSL verification for corporate environments
            self.logger.warning("⚠️ SSL verification disabled for Notion API calls")
            http_client = httpx.Client(verify=False)
            self.client = NotionClient(auth=access_token, client=http_client)

        self.logger.info(
            f"Initialized Notion Todos sync target with database {database_id} "
            f"(use_status_property={use_status_property})"
        )

    async def sync_item(self, item: SyncItem) -> SyncResult:
        """Sync a single item to Notion todos database."""
        try:
            if item.item_type != SyncItemType.TODO:
                return SyncResult(
                    status=SyncStatus.SKIPPED,
                    metadata={"reason": "This integration only syncs todos"},
                )

            return await self._sync_todo(item)

        except Exception as e:
            self.logger.error(f"Error syncing {item.item_type} to Notion todos: {e}")
            return SyncResult(status=SyncStatus.FAILED, error_message=str(e))

    async def _sync_todo(self, item: SyncItem) -> SyncResult:
        """
        Create a page in the todos database for this todo.

        Unlike the notebook integration which adds todos as blocks,
        this creates a proper database entry that can be tracked and managed.

        Adapts to database configuration:
        - If use_status_property=True: uses Status (status type) property
        - If use_status_property=False: uses Workflow (select type) property
        """
        try:
            todo_data = item.data
            todo_text = todo_data.get("text", "") or todo_data.get("todo_text", "")
            is_completed = todo_data.get("is_completed", False) or todo_data.get("completed", False)
            notebook_uuid = todo_data.get("notebook_uuid", "")
            notebook_name = todo_data.get("notebook_name", "")
            page_number = todo_data.get("page_number")
            confidence = todo_data.get("confidence")
            date_extracted = todo_data.get("date_extracted")
            source_link = todo_data.get("source_link")

            if not todo_text.strip():
                return SyncResult(
                    status=SyncStatus.SKIPPED,
                    metadata={"reason": "Empty todo text"},
                )

            # Determine workflow/status value based on completion
            workflow_value = "Done" if is_completed else "Not started"

            # Build base properties for the todo page
            properties = {
                "Task": {"title": [{"text": {"content": todo_text[:2000]}}]},  # Notion limit
                "Completed": {"checkbox": is_completed},
                "Notebook": {"rich_text": [{"text": {"content": notebook_name[:2000]}}]},
                "Notebook UUID": {"rich_text": [{"text": {"content": notebook_uuid}}]},
                "Tags": {"multi_select": [{"name": "remarkable"}]},
                "Synced At": {"date": {"start": datetime.utcnow().isoformat()}},
            }

            # Use Status (status type) or Workflow (select type) based on database
            if self.use_status_property:
                # Existing database with smart Status property
                properties["Status"] = {"status": {"name": workflow_value}}
            else:
                # New database with Workflow select property
                properties["Workflow"] = {"select": {"name": workflow_value}}

            # Add page number if available
            if page_number is not None:
                properties["Page"] = {"number": page_number}

            # Add confidence if available
            if confidence is not None:
                properties["Confidence"] = {"number": confidence}

            # Add date written if available
            if date_extracted:
                properties["Date Written"] = {"date": {"start": date_extracted}}

            # Add source link if available
            if source_link:
                properties["Link to Source"] = {"url": source_link}

            # Create page in todos database
            response = self.client.pages.create(
                parent={"database_id": self.database_id},
                properties=properties
            )

            page_id = response["id"]
            self.logger.info(f"Created todo page: {page_id} - '{todo_text[:50]}...'")

            return SyncResult(
                status=SyncStatus.SUCCESS,
                target_id=page_id,
                metadata={
                    "action": "todo_page_created",
                    "workflow": workflow_value,
                    "completed": is_completed,
                    "notebook": notebook_name,
                    "page_number": page_number,
                    "use_status_property": self.use_status_property,
                }
            )

        except Exception as e:
            self.logger.error(f"Error syncing todo: {e}")
            return SyncResult(status=SyncStatus.FAILED, error_message=str(e))

    async def check_duplicate(self, content_hash: str) -> Optional[str]:
        """
        Check if content with this hash already exists in Notion.

        For todos, we use the content hash to avoid duplicates.
        """
        # TODO: Implement duplicate checking using a hash property
        # For now, we'll let the sync manager handle this
        return None

    async def update_item(self, external_id: str, item: SyncItem) -> SyncResult:
        """Update an existing todo in Notion."""
        try:
            if item.item_type != SyncItemType.TODO:
                return SyncResult(
                    status=SyncStatus.FAILED,
                    error_message=f"Update not supported for {item.item_type}",
                )

            todo_data = item.data
            todo_text = todo_data.get("text", "") or todo_data.get("todo_text", "")
            is_completed = todo_data.get("is_completed", False) or todo_data.get("completed", False)
            notebook_name = todo_data.get("notebook_name", "")
            page_number = todo_data.get("page_number")
            confidence = todo_data.get("confidence")
            date_extracted = todo_data.get("date_extracted")
            source_link = todo_data.get("source_link")

            # Determine workflow/status value
            workflow_value = "Done" if is_completed else "Not started"

            # Update properties
            properties = {
                "Task": {"title": [{"text": {"content": todo_text[:2000]}}]},
                "Completed": {"checkbox": is_completed},
                "Notebook": {"rich_text": [{"text": {"content": notebook_name[:2000]}}]},
                "Synced At": {"date": {"start": datetime.utcnow().isoformat()}},
            }

            # Use Status (status type) or Workflow (select type) based on database
            if self.use_status_property:
                properties["Status"] = {"status": {"name": workflow_value}}
            else:
                properties["Workflow"] = {"select": {"name": workflow_value}}

            if page_number is not None:
                properties["Page"] = {"number": page_number}

            if confidence is not None:
                properties["Confidence"] = {"number": confidence}

            if date_extracted:
                properties["Date Written"] = {"date": {"start": date_extracted}}

            if source_link:
                properties["Link to Source"] = {"url": source_link}

            self.client.pages.update(page_id=external_id, properties=properties)

            self.logger.info(f"Updated todo page: {external_id}")
            return SyncResult(
                status=SyncStatus.SUCCESS,
                target_id=external_id,
                metadata={
                    "action": "updated",
                    "workflow": workflow_value,
                    "completed": is_completed,
                    "use_status_property": self.use_status_property,
                },
            )

        except Exception as e:
            self.logger.error(f"Error updating todo: {e}")
            return SyncResult(status=SyncStatus.FAILED, error_message=str(e))

    async def delete_item(self, external_id: str) -> SyncResult:
        """Delete (archive) a todo from Notion."""
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
        Validate connection to Notion todos database.

        Returns:
            True if connection is valid, False otherwise
        """
        try:
            # Test connection by querying the database
            self.client.databases.retrieve(database_id=self.database_id)
            return True
        except Exception as e:
            self.logger.error(f"Failed to validate Notion todos connection: {e}")
            return False

    def get_target_info(self) -> Dict[str, Any]:
        """Get information about this Notion todos target."""
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
                    "todos": True,
                },
            }
        except Exception as e:
            return {
                "target_name": self.target_name,
                "connected": False,
                "error": str(e),
            }
