"""Unit tests for NotionTodosSyncTarget.

Tests cover:
- Constructor with use_status_property flag
- Syncing todos with adaptive Status/Workflow properties
- Update operations
- Validation and error handling
"""

import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch

from app.core.sync_engine import SyncItem, SyncResult
from app.models.sync_record import SyncItemType, SyncStatus


class TestNotionTodosSyncTargetInit:
    """Tests for NotionTodosSyncTarget constructor."""

    def test_init_with_use_status_property_true(self):
        """Verify use_status_property=True is stored correctly."""
        with patch("app.integrations.notion_todos_sync.NotionClient"):
            with patch("app.integrations.notion_todos_sync.httpx.Client"):
                from app.integrations.notion_todos_sync import NotionTodosSyncTarget

                target = NotionTodosSyncTarget(
                    access_token="test-token",
                    database_id="db-123",
                    use_status_property=True,
                )

                assert target.use_status_property is True
                assert target.database_id == "db-123"
                assert target.target_name == "notion-todos"

    def test_init_with_use_status_property_false(self):
        """Verify use_status_property defaults to False."""
        with patch("app.integrations.notion_todos_sync.NotionClient"):
            with patch("app.integrations.notion_todos_sync.httpx.Client"):
                from app.integrations.notion_todos_sync import NotionTodosSyncTarget

                target = NotionTodosSyncTarget(
                    access_token="test-token",
                    database_id="db-123",
                    # use_status_property not specified, should default to False
                )

                assert target.use_status_property is False

    def test_init_with_ssl_verification_disabled(self):
        """Verify SSL verification can be disabled."""
        with patch("app.integrations.notion_todos_sync.NotionClient") as mock_notion:
            with patch("app.integrations.notion_todos_sync.httpx.Client") as mock_http:
                from app.integrations.notion_todos_sync import NotionTodosSyncTarget

                target = NotionTodosSyncTarget(
                    access_token="test-token",
                    database_id="db-123",
                    verify_ssl=False,
                )

                # When verify_ssl=False, httpx.Client should be called with verify=False
                mock_http.assert_called_once_with(verify=False)


class TestNotionTodosSyncTargetSyncTodo:
    """Tests for syncing todos with adaptive properties."""

    @pytest.mark.asyncio
    async def test_sync_todo_uses_workflow_when_use_status_false(self, sample_todo_sync_item):
        """Verify Workflow (select) property is used when use_status_property=False."""
        with patch("app.integrations.notion_todos_sync.NotionClient") as mock_notion_class:
            with patch("app.integrations.notion_todos_sync.httpx.Client"):
                mock_client = MagicMock()
                mock_client.pages.create.return_value = {"id": "todo-page-123"}
                mock_notion_class.return_value = mock_client

                from app.integrations.notion_todos_sync import NotionTodosSyncTarget

                target = NotionTodosSyncTarget(
                    access_token="test-token",
                    database_id="db-123",
                    use_status_property=False,  # Use Workflow
                )

                result = await target.sync_item(sample_todo_sync_item)

                assert result.status == SyncStatus.SUCCESS
                assert result.target_id == "todo-page-123"

                # Verify Workflow property was used
                call_args = mock_client.pages.create.call_args
                properties = call_args.kwargs["properties"]

                assert "Workflow" in properties
                assert properties["Workflow"] == {"select": {"name": "Not started"}}
                assert "Status" not in properties

    @pytest.mark.asyncio
    async def test_sync_todo_uses_status_when_use_status_true(self, sample_todo_sync_item):
        """Verify Status (status type) property is used when use_status_property=True."""
        with patch("app.integrations.notion_todos_sync.NotionClient") as mock_notion_class:
            with patch("app.integrations.notion_todos_sync.httpx.Client"):
                mock_client = MagicMock()
                mock_client.pages.create.return_value = {"id": "todo-page-456"}
                mock_notion_class.return_value = mock_client

                from app.integrations.notion_todos_sync import NotionTodosSyncTarget

                target = NotionTodosSyncTarget(
                    access_token="test-token",
                    database_id="db-123",
                    use_status_property=True,  # Use Status
                )

                result = await target.sync_item(sample_todo_sync_item)

                assert result.status == SyncStatus.SUCCESS

                # Verify Status property was used
                call_args = mock_client.pages.create.call_args
                properties = call_args.kwargs["properties"]

                assert "Status" in properties
                assert properties["Status"] == {"status": {"name": "Not started"}}
                assert "Workflow" not in properties

    @pytest.mark.asyncio
    async def test_sync_todo_includes_completed_checkbox(self, sample_todo_sync_item):
        """Verify Completed checkbox property is always included."""
        with patch("app.integrations.notion_todos_sync.NotionClient") as mock_notion_class:
            with patch("app.integrations.notion_todos_sync.httpx.Client"):
                mock_client = MagicMock()
                mock_client.pages.create.return_value = {"id": "todo-page-789"}
                mock_notion_class.return_value = mock_client

                from app.integrations.notion_todos_sync import NotionTodosSyncTarget

                target = NotionTodosSyncTarget(
                    access_token="test-token",
                    database_id="db-123",
                )

                await target.sync_item(sample_todo_sync_item)

                call_args = mock_client.pages.create.call_args
                properties = call_args.kwargs["properties"]

                assert "Completed" in properties
                assert properties["Completed"] == {"checkbox": False}

    @pytest.mark.asyncio
    async def test_sync_todo_includes_tags(self, sample_todo_sync_item):
        """Verify remarkable tag is included in Tags property."""
        with patch("app.integrations.notion_todos_sync.NotionClient") as mock_notion_class:
            with patch("app.integrations.notion_todos_sync.httpx.Client"):
                mock_client = MagicMock()
                mock_client.pages.create.return_value = {"id": "todo-page-abc"}
                mock_notion_class.return_value = mock_client

                from app.integrations.notion_todos_sync import NotionTodosSyncTarget

                target = NotionTodosSyncTarget(
                    access_token="test-token",
                    database_id="db-123",
                )

                await target.sync_item(sample_todo_sync_item)

                call_args = mock_client.pages.create.call_args
                properties = call_args.kwargs["properties"]

                assert "Tags" in properties
                assert properties["Tags"] == {"multi_select": [{"name": "remarkable"}]}

    @pytest.mark.asyncio
    async def test_sync_todo_optional_fields(self):
        """Verify optional fields (Page, Confidence, Date Written, Link to Source) are included when present."""
        with patch("app.integrations.notion_todos_sync.NotionClient") as mock_notion_class:
            with patch("app.integrations.notion_todos_sync.httpx.Client"):
                mock_client = MagicMock()
                mock_client.pages.create.return_value = {"id": "todo-page-opt"}
                mock_notion_class.return_value = mock_client

                from app.integrations.notion_todos_sync import NotionTodosSyncTarget

                target = NotionTodosSyncTarget(
                    access_token="test-token",
                    database_id="db-123",
                )

                # Create item with all optional fields
                item = SyncItem(
                    item_type=SyncItemType.TODO,
                    item_id="todo-opt",
                    content_hash="hash-opt",
                    data={
                        "text": "Todo with all fields",
                        "is_completed": True,
                        "notebook_uuid": "nb-opt",
                        "notebook_name": "Optional Notebook",
                        "page_number": 5,
                        "confidence": 0.87,
                        "date_extracted": "2026-01-20T14:30:00",
                        "source_link": "https://example.com/source",
                    },
                    source_table="todos",
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                )

                await target.sync_item(item)

                call_args = mock_client.pages.create.call_args
                properties = call_args.kwargs["properties"]

                # Verify optional fields
                assert "Page" in properties
                assert properties["Page"] == {"number": 5}

                assert "Confidence" in properties
                assert properties["Confidence"] == {"number": 0.87}

                assert "Date Written" in properties
                assert properties["Date Written"] == {"date": {"start": "2026-01-20T14:30:00"}}

                assert "Link to Source" in properties
                assert properties["Link to Source"] == {"url": "https://example.com/source"}

                # Completed should be True
                assert properties["Completed"] == {"checkbox": True}

                # Workflow should show "Done" since completed
                assert properties["Workflow"] == {"select": {"name": "Done"}}

    @pytest.mark.asyncio
    async def test_sync_todo_skips_empty_text(self):
        """Verify todos with empty text are skipped."""
        with patch("app.integrations.notion_todos_sync.NotionClient") as mock_notion_class:
            with patch("app.integrations.notion_todos_sync.httpx.Client"):
                mock_client = MagicMock()
                mock_notion_class.return_value = mock_client

                from app.integrations.notion_todos_sync import NotionTodosSyncTarget

                target = NotionTodosSyncTarget(
                    access_token="test-token",
                    database_id="db-123",
                )

                item = SyncItem(
                    item_type=SyncItemType.TODO,
                    item_id="empty-todo",
                    content_hash="hash-empty",
                    data={
                        "text": "   ",  # Empty/whitespace only
                        "notebook_uuid": "nb-123",
                        "notebook_name": "Test",
                    },
                    source_table="todos",
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                )

                result = await target.sync_item(item)

                assert result.status == SyncStatus.SKIPPED
                assert "Empty todo text" in result.metadata.get("reason", "")
                mock_client.pages.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_sync_todo_truncates_long_text(self):
        """Verify todo text is truncated to 2000 chars (Notion limit)."""
        with patch("app.integrations.notion_todos_sync.NotionClient") as mock_notion_class:
            with patch("app.integrations.notion_todos_sync.httpx.Client"):
                mock_client = MagicMock()
                mock_client.pages.create.return_value = {"id": "todo-long"}
                mock_notion_class.return_value = mock_client

                from app.integrations.notion_todos_sync import NotionTodosSyncTarget

                target = NotionTodosSyncTarget(
                    access_token="test-token",
                    database_id="db-123",
                )

                long_text = "A" * 3000  # Exceeds 2000 char limit

                item = SyncItem(
                    item_type=SyncItemType.TODO,
                    item_id="long-todo",
                    content_hash="hash-long",
                    data={
                        "text": long_text,
                        "notebook_uuid": "nb-123",
                        "notebook_name": "Test",
                    },
                    source_table="todos",
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                )

                await target.sync_item(item)

                call_args = mock_client.pages.create.call_args
                properties = call_args.kwargs["properties"]

                # Task title should be truncated
                task_content = properties["Task"]["title"][0]["text"]["content"]
                assert len(task_content) == 2000

    @pytest.mark.asyncio
    async def test_sync_todo_skips_non_todo_items(self, sample_notebook_sync_item):
        """Verify non-TODO items are skipped."""
        with patch("app.integrations.notion_todos_sync.NotionClient") as mock_notion_class:
            with patch("app.integrations.notion_todos_sync.httpx.Client"):
                mock_client = MagicMock()
                mock_notion_class.return_value = mock_client

                from app.integrations.notion_todos_sync import NotionTodosSyncTarget

                target = NotionTodosSyncTarget(
                    access_token="test-token",
                    database_id="db-123",
                )

                result = await target.sync_item(sample_notebook_sync_item)

                assert result.status == SyncStatus.SKIPPED
                assert "only syncs todos" in result.metadata.get("reason", "")


class TestNotionTodosSyncTargetUpdateTodo:
    """Tests for updating existing todos."""

    @pytest.mark.asyncio
    async def test_update_todo_uses_workflow_when_use_status_false(self, sample_todo_sync_item):
        """Verify update uses Workflow when use_status_property=False."""
        with patch("app.integrations.notion_todos_sync.NotionClient") as mock_notion_class:
            with patch("app.integrations.notion_todos_sync.httpx.Client"):
                mock_client = MagicMock()
                mock_client.pages.update.return_value = {"id": "existing-todo-123"}
                mock_notion_class.return_value = mock_client

                from app.integrations.notion_todos_sync import NotionTodosSyncTarget

                target = NotionTodosSyncTarget(
                    access_token="test-token",
                    database_id="db-123",
                    use_status_property=False,
                )

                result = await target.update_item("existing-todo-123", sample_todo_sync_item)

                assert result.status == SyncStatus.SUCCESS

                call_args = mock_client.pages.update.call_args
                properties = call_args.kwargs["properties"]

                assert "Workflow" in properties
                assert "Status" not in properties

    @pytest.mark.asyncio
    async def test_update_todo_uses_status_when_use_status_true(self, sample_todo_sync_item):
        """Verify update uses Status when use_status_property=True."""
        with patch("app.integrations.notion_todos_sync.NotionClient") as mock_notion_class:
            with patch("app.integrations.notion_todos_sync.httpx.Client"):
                mock_client = MagicMock()
                mock_client.pages.update.return_value = {"id": "existing-todo-456"}
                mock_notion_class.return_value = mock_client

                from app.integrations.notion_todos_sync import NotionTodosSyncTarget

                target = NotionTodosSyncTarget(
                    access_token="test-token",
                    database_id="db-123",
                    use_status_property=True,
                )

                result = await target.update_item("existing-todo-456", sample_todo_sync_item)

                assert result.status == SyncStatus.SUCCESS

                call_args = mock_client.pages.update.call_args
                properties = call_args.kwargs["properties"]

                assert "Status" in properties
                assert "Workflow" not in properties

    @pytest.mark.asyncio
    async def test_update_todo_error_handling(self, sample_todo_sync_item):
        """Test error handling during todo update."""
        with patch("app.integrations.notion_todos_sync.NotionClient") as mock_notion_class:
            with patch("app.integrations.notion_todos_sync.httpx.Client"):
                mock_client = MagicMock()
                mock_client.pages.update.side_effect = Exception("API Error: Page not found")
                mock_notion_class.return_value = mock_client

                from app.integrations.notion_todos_sync import NotionTodosSyncTarget

                target = NotionTodosSyncTarget(
                    access_token="test-token",
                    database_id="db-123",
                )

                result = await target.update_item("nonexistent-todo", sample_todo_sync_item)

                assert result.status == SyncStatus.FAILED
                assert "API Error" in result.error_message

    @pytest.mark.asyncio
    async def test_update_todo_rejects_non_todo_items(self, sample_notebook_sync_item):
        """Verify update rejects non-TODO items."""
        with patch("app.integrations.notion_todos_sync.NotionClient") as mock_notion_class:
            with patch("app.integrations.notion_todos_sync.httpx.Client"):
                mock_client = MagicMock()
                mock_notion_class.return_value = mock_client

                from app.integrations.notion_todos_sync import NotionTodosSyncTarget

                target = NotionTodosSyncTarget(
                    access_token="test-token",
                    database_id="db-123",
                )

                result = await target.update_item("page-123", sample_notebook_sync_item)

                assert result.status == SyncStatus.FAILED
                assert "not supported" in result.error_message


class TestNotionTodosSyncTargetValidation:
    """Tests for connection validation."""

    @pytest.mark.asyncio
    async def test_validate_connection_success(self):
        """Test successful connection validation."""
        with patch("app.integrations.notion_todos_sync.NotionClient") as mock_notion_class:
            with patch("app.integrations.notion_todos_sync.httpx.Client"):
                mock_client = MagicMock()
                mock_client.databases.retrieve.return_value = {"id": "db-123"}
                mock_notion_class.return_value = mock_client

                from app.integrations.notion_todos_sync import NotionTodosSyncTarget

                target = NotionTodosSyncTarget(
                    access_token="test-token",
                    database_id="db-123",
                )

                result = await target.validate_connection()

                assert result is True
                mock_client.databases.retrieve.assert_called_once_with(database_id="db-123")

    @pytest.mark.asyncio
    async def test_validate_connection_failure(self):
        """Test failed connection validation."""
        with patch("app.integrations.notion_todos_sync.NotionClient") as mock_notion_class:
            with patch("app.integrations.notion_todos_sync.httpx.Client"):
                mock_client = MagicMock()
                mock_client.databases.retrieve.side_effect = Exception("Database not found")
                mock_notion_class.return_value = mock_client

                from app.integrations.notion_todos_sync import NotionTodosSyncTarget

                target = NotionTodosSyncTarget(
                    access_token="test-token",
                    database_id="invalid-db",
                )

                result = await target.validate_connection()

                assert result is False


class TestNotionTodosSyncTargetDeleteItem:
    """Tests for deleting/archiving todos."""

    @pytest.mark.asyncio
    async def test_delete_item_archives_page(self):
        """Verify delete_item archives the Notion page."""
        with patch("app.integrations.notion_todos_sync.NotionClient") as mock_notion_class:
            with patch("app.integrations.notion_todos_sync.httpx.Client"):
                mock_client = MagicMock()
                mock_client.pages.update.return_value = {"id": "todo-to-delete", "archived": True}
                mock_notion_class.return_value = mock_client

                from app.integrations.notion_todos_sync import NotionTodosSyncTarget

                target = NotionTodosSyncTarget(
                    access_token="test-token",
                    database_id="db-123",
                )

                result = await target.delete_item("todo-to-delete")

                assert result.status == SyncStatus.SUCCESS
                assert result.metadata.get("action") == "archived"

                mock_client.pages.update.assert_called_once_with(
                    page_id="todo-to-delete",
                    archived=True,
                )

    @pytest.mark.asyncio
    async def test_delete_item_handles_error(self):
        """Test error handling during deletion."""
        with patch("app.integrations.notion_todos_sync.NotionClient") as mock_notion_class:
            with patch("app.integrations.notion_todos_sync.httpx.Client"):
                mock_client = MagicMock()
                mock_client.pages.update.side_effect = Exception("Cannot archive page")
                mock_notion_class.return_value = mock_client

                from app.integrations.notion_todos_sync import NotionTodosSyncTarget

                target = NotionTodosSyncTarget(
                    access_token="test-token",
                    database_id="db-123",
                )

                result = await target.delete_item("problem-todo")

                assert result.status == SyncStatus.FAILED
                assert "Cannot archive" in result.error_message


class TestNotionTodosSyncTargetGetInfo:
    """Tests for get_target_info method."""

    def test_get_target_info_connected(self):
        """Test get_target_info when connected."""
        with patch("app.integrations.notion_todos_sync.NotionClient") as mock_notion_class:
            with patch("app.integrations.notion_todos_sync.httpx.Client"):
                mock_client = MagicMock()
                mock_client.databases.retrieve.return_value = {
                    "id": "db-123",
                    "title": [{"text": {"content": "My Todos"}}],
                }
                mock_notion_class.return_value = mock_client

                from app.integrations.notion_todos_sync import NotionTodosSyncTarget

                target = NotionTodosSyncTarget(
                    access_token="test-token",
                    database_id="db-123",
                )

                info = target.get_target_info()

                assert info["connected"] is True
                assert info["target_name"] == "notion-todos"
                assert info["database_id"] == "db-123"
                assert info["database_title"] == "My Todos"
                assert info["capabilities"]["todos"] is True

    def test_get_target_info_disconnected(self):
        """Test get_target_info when disconnected."""
        with patch("app.integrations.notion_todos_sync.NotionClient") as mock_notion_class:
            with patch("app.integrations.notion_todos_sync.httpx.Client"):
                mock_client = MagicMock()
                mock_client.databases.retrieve.side_effect = Exception("Connection failed")
                mock_notion_class.return_value = mock_client

                from app.integrations.notion_todos_sync import NotionTodosSyncTarget

                target = NotionTodosSyncTarget(
                    access_token="test-token",
                    database_id="db-123",
                )

                info = target.get_target_info()

                assert info["connected"] is False
                assert "error" in info
