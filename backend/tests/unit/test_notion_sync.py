"""Unit tests for NotionSyncTarget.

Tests cover:
- Notebook page creation with full metadata
- Notebook metadata-only syncing
- Page text syncing with block management
- Deduplication using page_uuid
- Error handling for archived blocks and rate limiting
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import httpx
import pytest
from notion_client.errors import APIResponseError

from app.core.sync_engine import SyncErrorKind, SyncItem
from app.models.sync_record import SyncItemType, SyncStatus


class TestNotionSyncTargetInit:
    """Tests for NotionSyncTarget constructor."""

    def test_init_with_ssl_disabled(self):
        """Verify SSL verification can be disabled."""
        with patch("app.integrations.notion_sync.NotionClient"):
            with patch("app.integrations.notion_sync.httpx.Client") as mock_http:
                from app.integrations.notion_sync import NotionSyncTarget

                target = NotionSyncTarget(
                    access_token="test-token",
                    database_id="db-123",
                    verify_ssl=False,
                )

                # Should use httpx client with SSL disabled
                mock_http.assert_called_once_with(verify=False)
                assert target.database_id == "db-123"
                assert target.target_name == "notion"

    def test_init_with_ssl_enabled(self):
        """Verify SSL verification works when enabled."""
        with patch("app.integrations.notion_sync.NotionClient") as mock_notion:
            from app.integrations.notion_sync import NotionSyncTarget

            NotionSyncTarget(
                access_token="test-token",
                database_id="db-123",
                verify_ssl=True,
            )

            # Should NOT use httpx client (SSL enabled = default behavior)
            mock_notion.assert_called_once()


class TestNotionSyncTargetNotebookSync:
    """Tests for notebook page creation and metadata syncing."""

    @pytest.mark.asyncio
    async def test_create_notebook_page_with_metadata(self):
        """The notebook page is created with all metadata fields and no page toggles."""
        with patch("app.integrations.notion_sync.NotionClient") as mock_notion_class:
            with patch("app.integrations.notion_sync.httpx.Client"):
                mock_client = MagicMock()
                mock_client.pages.create.return_value = {"id": "notebook-page-123"}
                mock_notion_class.return_value = mock_client

                from app.integrations.notion_sync import NotionSyncTarget

                target = NotionSyncTarget(
                    access_token="test-token",
                    database_id="db-123",
                )

                page_id = await target._create_notion_page(
                    notebook_uuid="nb-123",
                    title="Test Notebook",
                    full_path="Work/Projects/Client A",
                    last_opened="2026-01-15T10:00:00",
                    last_modified="2026-01-15T09:00:00",
                )

                assert page_id == "notebook-page-123"

                call_args = mock_client.pages.create.call_args
                properties = call_args.kwargs["properties"]

                # Core properties
                assert properties["Name"]["title"][0]["text"]["content"] == "Test Notebook"
                assert properties["UUID"]["rich_text"][0]["text"]["content"] == "nb-123"
                assert properties["Path"]["rich_text"][0]["text"]["content"] == "Work/Projects/Client A"
                assert properties["Pages"]["number"] == 0

                # Tags from path
                tag_names = [t["name"] for t in properties["Tags"]["multi_select"]]
                assert tag_names == ["Work", "Projects", "Client A"]

                # Timestamps
                assert "Last Opened" in properties
                assert "Last Modified" in properties
                assert "Synced At" in properties

                # Status
                assert properties["Status"]["select"]["name"] == "Synced"

                # Only the content heading; page toggles come from page syncs.
                children = call_args.kwargs["children"]
                assert [b["type"] for b in children] == ["heading_2"]

    @pytest.mark.asyncio
    async def test_sync_notebook_metadata_only(self):
        """Verify metadata-only sync updates properties without touching content."""
        with patch("app.integrations.notion_sync.NotionClient") as mock_notion_class:
            with patch("app.integrations.notion_sync.httpx.Client"):
                mock_client = MagicMock()
                mock_client.pages.update.return_value = {"id": "existing-page-789"}
                mock_notion_class.return_value = mock_client

                # Mock finding existing page
                with patch("httpx.post") as mock_post:
                    mock_response = MagicMock()
                    mock_response.status_code = 200
                    mock_response.json.return_value = {
                        "results": [{"id": "existing-page-789"}]
                    }
                    mock_post.return_value = mock_response

                    from app.integrations.notion_sync import NotionSyncTarget

                    target = NotionSyncTarget(
                        access_token="test-token",
                        database_id="db-123",
                    )

                    # Create metadata-only sync item
                    item = SyncItem(
                        item_type=SyncItemType.NOTEBOOK_METADATA,
                        item_id="nb-meta-123",
                        content_hash="meta-hash-123",
                        data={
                            "notebook_uuid": "nb-123",
                            "title": "Updated Notebook",
                            "full_path": "New/Path",
                            "page_count": 5,
                            "last_opened_at": "2026-01-20T10:00:00",
                            "last_modified_at": "2026-01-20T09:00:00",
                        },
                        source_table="notebooks",
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow(),
                    )

                    result = await target.sync_item(item)

                    assert result.status == SyncStatus.SUCCESS
                    assert result.metadata.get("action") == "metadata_updated"

                    # Verify only properties were updated (no block operations)
                    mock_client.pages.update.assert_called_once()
                    mock_client.blocks.children.list.assert_not_called()
                    mock_client.blocks.children.append.assert_not_called()

    @pytest.mark.asyncio
    async def test_sync_notebook_metadata_skipped_when_not_synced(self):
        """Verify metadata-only sync is skipped when notebook not yet synced."""
        with patch("app.integrations.notion_sync.NotionClient") as mock_notion_class:
            with patch("app.integrations.notion_sync.httpx.Client"):
                mock_client = MagicMock()
                mock_client.search.return_value = {"results": []}
                mock_notion_class.return_value = mock_client

                # Mock no existing page found
                with patch("httpx.post") as mock_post:
                    mock_response = MagicMock()
                    mock_response.status_code = 200
                    mock_response.json.return_value = {"results": []}
                    mock_post.return_value = mock_response

                    from app.integrations.notion_sync import NotionSyncTarget

                    target = NotionSyncTarget(
                        access_token="test-token",
                        database_id="db-123",
                    )

                    item = SyncItem(
                        item_type=SyncItemType.NOTEBOOK_METADATA,
                        item_id="nb-new",
                        content_hash="new-hash",
                        data={
                            "notebook_uuid": "nb-new",
                            "title": "New Notebook",
                            "page_count": 1,
                        },
                        source_table="notebooks",
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow(),
                    )

                    result = await target.sync_item(item)

                    assert result.status == SyncStatus.SKIPPED
                    assert "not yet synced" in result.metadata.get("reason", "")


class TestNotionSyncTargetPageTextSync:
    """Tests for page text syncing."""

    @pytest.mark.asyncio
    async def test_sync_page_text_creates_blocks(self, sample_page_text_sync_item):
        """Verify page text sync creates toggle blocks."""
        with patch("app.integrations.notion_sync.NotionClient") as mock_notion_class:
            with patch("app.integrations.notion_sync.httpx.Client"):
                mock_client = MagicMock()
                mock_client.blocks.children.list.return_value = {"results": [], "has_more": False}
                mock_client.blocks.children.append.return_value = {
                    "results": [{"id": "new-block-123"}]
                }
                mock_notion_class.return_value = mock_client

                # Mock finding existing notebook page
                with patch("httpx.post") as mock_post:
                    mock_response = MagicMock()
                    mock_response.status_code = 200
                    mock_response.json.return_value = {
                        "results": [{"id": "parent-page-123"}]
                    }
                    mock_post.return_value = mock_response

                    from app.integrations.notion_sync import NotionSyncTarget

                    target = NotionSyncTarget(
                        access_token="test-token",
                        database_id="db-123",
                    )

                    result = await target.sync_item(sample_page_text_sync_item)

                    assert result.status == SyncStatus.SUCCESS
                    assert result.metadata.get("action") == "page_created"
                    assert result.metadata.get("page_number") == 1

                    # Verify block was created
                    mock_client.blocks.children.append.assert_called()
                    call_args = mock_client.blocks.children.append.call_args
                    children = call_args.kwargs["children"]

                    # Should be a toggle block
                    assert len(children) == 1
                    assert children[0]["type"] == "toggle"

    @pytest.mark.asyncio
    async def test_sync_page_text_updates_existing_blocks(self):
        """Verify page text sync updates existing blocks when block_id provided."""
        with patch("app.integrations.notion_sync.NotionClient") as mock_notion_class:
            with patch("app.integrations.notion_sync.httpx.Client"):
                mock_client = MagicMock()
                mock_client.blocks.children.list.return_value = {
                    "results": [
                        {"id": "existing-block-123", "type": "toggle", "toggle": {"rich_text": [{"text": {"content": "📄 Page 1"}}]}}
                    ],
                    "has_more": False,
                }
                mock_client.blocks.delete.return_value = {}
                mock_client.blocks.children.append.return_value = {
                    "results": [{"id": "updated-block-456"}]
                }
                mock_notion_class.return_value = mock_client

                from app.integrations.notion_sync import NotionSyncTarget

                target = NotionSyncTarget(
                    access_token="test-token",
                    database_id="db-123",
                )

                # Item with existing block ID
                item = SyncItem(
                    item_type=SyncItemType.PAGE_TEXT,
                    item_id="page-update",
                    content_hash="updated-hash",
                    data={
                        "text": "Updated OCR text",
                        "page_number": 1,
                        "notebook_uuid": "nb-123",
                        "notebook_name": "Test",
                        "existing_block_id": "existing-block-123",
                        "existing_notebook_page_id": "parent-page-123",
                    },
                    source_table="pages",
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                )

                result = await target.sync_item(item)

                assert result.status == SyncStatus.SUCCESS
                # Old block should be deleted
                mock_client.blocks.delete.assert_called_with(block_id="existing-block-123")
                # New block should be created
                mock_client.blocks.children.append.assert_called()

    @pytest.mark.asyncio
    async def test_sync_page_text_skips_empty_content(self):
        """Verify empty page content is skipped."""
        with patch("app.integrations.notion_sync.NotionClient") as mock_notion_class:
            with patch("app.integrations.notion_sync.httpx.Client"):
                mock_client = MagicMock()
                mock_notion_class.return_value = mock_client

                from app.integrations.notion_sync import NotionSyncTarget

                target = NotionSyncTarget(
                    access_token="test-token",
                    database_id="db-123",
                )

                item = SyncItem(
                    item_type=SyncItemType.PAGE_TEXT,
                    item_id="empty-page",
                    content_hash="empty-hash",
                    data={
                        "text": "   ",  # Whitespace only
                        "page_number": 1,
                        "notebook_uuid": "nb-123",
                    },
                    source_table="pages",
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                )

                result = await target.sync_item(item)

                assert result.status == SyncStatus.SKIPPED
                assert "Empty page content" in result.metadata.get("reason", "")

    @pytest.mark.asyncio
    async def test_sync_page_text_auto_creates_notebook_page(self):
        """Verify notebook page is auto-created if it doesn't exist."""
        with patch("app.integrations.notion_sync.NotionClient") as mock_notion_class:
            with patch("app.integrations.notion_sync.httpx.Client"):
                mock_client = MagicMock()
                mock_client.pages.create.return_value = {"id": "auto-created-page"}
                mock_client.blocks.children.list.return_value = {"results": [], "has_more": False}
                mock_client.blocks.children.append.return_value = {
                    "results": [{"id": "block-123"}]
                }
                mock_client.search.return_value = {"results": []}
                mock_notion_class.return_value = mock_client

                # Mock no existing page
                with patch("httpx.post") as mock_post:
                    mock_response = MagicMock()
                    mock_response.status_code = 200
                    mock_response.json.return_value = {"results": []}
                    mock_post.return_value = mock_response

                    from app.integrations.notion_sync import NotionSyncTarget

                    target = NotionSyncTarget(
                        access_token="test-token",
                        database_id="db-123",
                    )

                    item = SyncItem(
                        item_type=SyncItemType.PAGE_TEXT,
                        item_id="orphan-page",
                        content_hash="orphan-hash",
                        data={
                            "text": "OCR text for orphan page",
                            "page_number": 1,
                            "notebook_uuid": "nb-orphan",
                            "notebook_name": "Orphan Notebook",
                            "existing_block_id": None,
                            "existing_notebook_page_id": None,
                        },
                        source_table="pages",
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow(),
                    )

                    result = await target.sync_item(item)

                    assert result.status == SyncStatus.SUCCESS
                    assert result.metadata.get("notebook_created") is True

                    # Verify notebook page was created
                    mock_client.pages.create.assert_called()


class TestNotionSyncTargetDeduplication:
    """Tests for deduplication logic."""

    @pytest.mark.asyncio
    async def test_find_existing_page_uses_uuid_not_content_hash(self):
        """Verify find_existing_page queries by UUID, not content_hash."""
        with patch("app.integrations.notion_sync.NotionClient") as mock_notion_class:
            with patch("app.integrations.notion_sync.httpx.Client"):
                mock_client = MagicMock()
                mock_client.search.return_value = {"results": []}
                mock_notion_class.return_value = mock_client

                with patch("httpx.post") as mock_post:
                    mock_response = MagicMock()
                    mock_response.status_code = 200
                    mock_response.json.return_value = {
                        "results": [{"id": "found-page-123"}]
                    }
                    mock_post.return_value = mock_response

                    from app.integrations.notion_sync import NotionSyncTarget

                    target = NotionSyncTarget(
                        access_token="test-token",
                        database_id="db-123",
                    )

                    result = await target.find_existing_page("my-notebook-uuid")

                    assert result == "found-page-123"

                    # Verify the query was made by UUID property
                    call_args = mock_post.call_args
                    json_body = call_args.kwargs["json"]

                    assert json_body["filter"]["property"] == "UUID"
                    assert json_body["filter"]["rich_text"]["equals"] == "my-notebook-uuid"

    @pytest.mark.asyncio
    async def test_find_existing_page_falls_back_to_search(self):
        """Verify fallback to search when database query fails."""
        with patch("app.integrations.notion_sync.NotionClient") as mock_notion_class:
            with patch("app.integrations.notion_sync.httpx.Client"):
                mock_client = MagicMock()
                mock_client.search.return_value = {
                    "results": [
                        {
                            "id": "fallback-page-456",
                            "parent": {"database_id": "db-123"},
                            "properties": {
                                "Name": {
                                    "title": [{"text": {"content": "Notebook my-uuid"}}]
                                }
                            },
                        }
                    ]
                }
                mock_notion_class.return_value = mock_client

                with patch("httpx.post") as mock_post:
                    # Database query fails
                    mock_response = MagicMock()
                    mock_response.status_code = 400
                    mock_response.text = "Bad request"
                    mock_post.return_value = mock_response

                    from app.integrations.notion_sync import NotionSyncTarget

                    target = NotionSyncTarget(
                        access_token="test-token",
                        database_id="db-123",
                    )

                    result = await target.find_existing_page("my-uuid")

                    assert result == "fallback-page-456"

                    # Verify search was called with UUID prefix
                    mock_client.search.assert_called()


class TestNotionSyncTargetErrorHandling:
    """Tests for error handling scenarios."""

    @pytest.mark.asyncio
    async def test_handles_archived_block_error(self):
        """Test handling of 'Can't edit block that is archived' error."""
        with patch("app.integrations.notion_sync.NotionClient") as mock_notion_class:
            with patch("app.integrations.notion_sync.httpx.Client"):
                mock_client = MagicMock()
                mock_client.blocks.children.list.return_value = {
                    "results": [
                        {"id": "archived-block", "type": "toggle", "toggle": {"rich_text": [{"text": {"content": "📄 Page 1"}}]}}
                    ],
                    "has_more": False,
                }
                # Delete fails because block is archived
                mock_client.blocks.delete.side_effect = Exception("Can't edit block that is archived")
                mock_client.blocks.children.append.return_value = {
                    "results": [{"id": "new-block-789"}]
                }
                mock_notion_class.return_value = mock_client

                from app.integrations.notion_sync import NotionSyncTarget

                target = NotionSyncTarget(
                    access_token="test-token",
                    database_id="db-123",
                )

                item = SyncItem(
                    item_type=SyncItemType.PAGE_TEXT,
                    item_id="archived-page",
                    content_hash="archived-hash",
                    data={
                        "text": "New text for archived block",
                        "page_number": 1,
                        "notebook_uuid": "nb-123",
                        "notebook_name": "Test",
                        "existing_block_id": "archived-block",
                        "existing_notebook_page_id": "parent-123",
                    },
                    source_table="pages",
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                )

                result = await target.sync_item(item)

                # Should still succeed - archived block is treated as deleted
                assert result.status == SyncStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_create_notion_page_returns_none_on_error(self):
        """_create_notion_page swallows the error and returns None."""
        with patch("app.integrations.notion_sync.NotionClient") as mock_notion_class:
            with patch("app.integrations.notion_sync.httpx.Client"):
                mock_client = MagicMock()
                mock_client.pages.create.side_effect = Exception("API error: invalid database")
                mock_notion_class.return_value = mock_client

                from app.integrations.notion_sync import NotionSyncTarget

                target = NotionSyncTarget(
                    access_token="test-token",
                    database_id="db-123",
                )

                assert await target._create_notion_page("nb-123", "Test", "") is None

    @pytest.mark.asyncio
    async def test_handles_unsupported_item_type(self):
        """Test handling of unsupported item types."""
        with patch("app.integrations.notion_sync.NotionClient") as mock_notion_class:
            with patch("app.integrations.notion_sync.httpx.Client"):
                mock_client = MagicMock()
                mock_notion_class.return_value = mock_client

                from app.integrations.notion_sync import NotionSyncTarget

                target = NotionSyncTarget(
                    access_token="test-token",
                    database_id="db-123",
                )

                # Highlight items should be skipped
                item = SyncItem(
                    item_type=SyncItemType.HIGHLIGHT,
                    item_id="highlight-123",
                    content_hash="highlight-hash",
                    data={"text": "Highlighted text"},
                    source_table="highlights",
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                )

                result = await target.sync_item(item)

                assert result.status == SyncStatus.SKIPPED

    @pytest.mark.asyncio
    async def test_todo_items_redirected(self, sample_todo_sync_item):
        """Test that TODO items are skipped with redirect message."""
        with patch("app.integrations.notion_sync.NotionClient") as mock_notion_class:
            with patch("app.integrations.notion_sync.httpx.Client"):
                mock_client = MagicMock()
                mock_notion_class.return_value = mock_client

                from app.integrations.notion_sync import NotionSyncTarget

                target = NotionSyncTarget(
                    access_token="test-token",
                    database_id="db-123",
                )

                result = await target.sync_item(sample_todo_sync_item)

                assert result.status == SyncStatus.SKIPPED
                assert "notion-todos" in result.metadata.get("reason", "")


class TestNotionSyncTargetValidation:
    """Tests for validation methods."""

    @pytest.mark.asyncio
    async def test_validate_connection_success(self):
        """Test successful connection validation."""
        with patch("app.integrations.notion_sync.NotionClient") as mock_notion_class:
            with patch("app.integrations.notion_sync.httpx.Client"):
                mock_client = MagicMock()
                mock_client.databases.retrieve.return_value = {"id": "db-123"}
                mock_notion_class.return_value = mock_client

                from app.integrations.notion_sync import NotionSyncTarget

                target = NotionSyncTarget(
                    access_token="test-token",
                    database_id="db-123",
                )

                result = await target.validate_connection()

                assert result is True

    @pytest.mark.asyncio
    async def test_validate_connection_failure(self):
        """Test failed connection validation."""
        with patch("app.integrations.notion_sync.NotionClient") as mock_notion_class:
            with patch("app.integrations.notion_sync.httpx.Client"):
                mock_client = MagicMock()
                mock_client.databases.retrieve.side_effect = Exception("Not found")
                mock_notion_class.return_value = mock_client

                from app.integrations.notion_sync import NotionSyncTarget

                target = NotionSyncTarget(
                    access_token="test-token",
                    database_id="invalid-db",
                )

                result = await target.validate_connection()

                assert result is False


class TestNotionSyncTargetHelperMethods:
    """Tests for helper methods."""

    def test_extract_tags_from_path(self):
        """Test tag extraction from folder path."""
        with patch("app.integrations.notion_sync.NotionClient"):
            with patch("app.integrations.notion_sync.httpx.Client"):
                from app.integrations.notion_sync import NotionSyncTarget

                target = NotionSyncTarget(
                    access_token="test-token",
                    database_id="db-123",
                )

                # Normal path
                tags = target._extract_tags_from_path("Work/Projects/Client A")
                assert tags == ["Work", "Projects", "Client A"]

                # Path with leading/trailing slashes
                tags = target._extract_tags_from_path("/Folder/Subfolder/")
                assert tags == ["Folder", "Subfolder"]

                # Empty path
                tags = target._extract_tags_from_path("")
                assert tags == []

                # Root path
                tags = target._extract_tags_from_path("/")
                assert tags == []

    def test_get_target_info_connected(self):
        """Test get_target_info when connected."""
        with patch("app.integrations.notion_sync.NotionClient") as mock_notion_class:
            with patch("app.integrations.notion_sync.httpx.Client"):
                mock_client = MagicMock()
                mock_client.databases.retrieve.return_value = {
                    "id": "db-123",
                    "title": [{"text": {"content": "My Notebooks"}}],
                }
                mock_notion_class.return_value = mock_client

                from app.integrations.notion_sync import NotionSyncTarget

                target = NotionSyncTarget(
                    access_token="test-token",
                    database_id="db-123",
                )

                info = target.get_target_info()

                assert info["connected"] is True
                assert info["target_name"] == "notion"
                assert info["database_id"] == "db-123"
                assert info["capabilities"]["notebooks"] is True
                assert info["capabilities"]["page_text"] is True

    def test_get_target_info_disconnected(self):
        """Test get_target_info when disconnected."""
        with patch("app.integrations.notion_sync.NotionClient") as mock_notion_class:
            with patch("app.integrations.notion_sync.httpx.Client"):
                mock_client = MagicMock()
                mock_client.databases.retrieve.side_effect = Exception("Auth failed")
                mock_notion_class.return_value = mock_client

                from app.integrations.notion_sync import NotionSyncTarget

                target = NotionSyncTarget(
                    access_token="test-token",
                    database_id="db-123",
                )

                info = target.get_target_info()

                assert info["connected"] is False
                assert "error" in info


class TestNotionSyncTargetDeleteItem:
    """Tests for delete_item method."""

    @pytest.mark.asyncio
    async def test_delete_item_archives_page(self):
        """Verify delete_item archives the page."""
        with patch("app.integrations.notion_sync.NotionClient") as mock_notion_class:
            with patch("app.integrations.notion_sync.httpx.Client"):
                mock_client = MagicMock()
                mock_client.pages.update.return_value = {"id": "page-to-delete", "archived": True}
                mock_notion_class.return_value = mock_client

                from app.integrations.notion_sync import NotionSyncTarget

                target = NotionSyncTarget(
                    access_token="test-token",
                    database_id="db-123",
                )

                result = await target.delete_item("page-to-delete")

                assert result.status == SyncStatus.SUCCESS
                assert result.metadata.get("action") == "archived"

                mock_client.pages.update.assert_called_once_with(
                    page_id="page-to-delete",
                    archived=True,
                )

    @pytest.mark.asyncio
    async def test_delete_item_handles_error(self):
        """Test error handling during deletion."""
        with patch("app.integrations.notion_sync.NotionClient") as mock_notion_class:
            with patch("app.integrations.notion_sync.httpx.Client"):
                mock_client = MagicMock()
                mock_client.pages.update.side_effect = Exception("Cannot archive")
                mock_notion_class.return_value = mock_client

                from app.integrations.notion_sync import NotionSyncTarget

                target = NotionSyncTarget(
                    access_token="test-token",
                    database_id="db-123",
                )

                result = await target.delete_item("problem-page")

                assert result.status == SyncStatus.FAILED
                assert "Cannot archive" in result.error_message


# ---------------------------------------------------------------------------
# Retry-safe writes and typed errors
# ---------------------------------------------------------------------------

PAGE_UUID = "aaaabbbb-1111-2222-3333-444455556666"
MARKER = " · aaaabbbb"


def api_error(status, code, message="Notion error", headers=None):
    """A real notion_client APIResponseError, as the SDK raises it."""
    request = httpx.Request("POST", "https://api.notion.com/v1/test")
    response = httpx.Response(
        status,
        headers=headers or {},
        json={"object": "error", "status": status, "code": code, "message": message},
        request=request,
    )
    return APIResponseError(response, message, code)


def query_response(status, results=None, headers=None, code=None):
    """Response of the direct databases/query HTTP call in find_existing_page."""
    body = {"results": results or []} if status == 200 else {"code": code, "message": "x"}
    return httpx.Response(
        status,
        headers=headers or {},
        json=body,
        request=httpx.Request("POST", "https://api.notion.com/v1/databases/db/query"),
    )


def heading(block_id="heading"):
    return {"id": block_id, "type": "heading_2", "heading_2": {"rich_text": []}}


def toggle(block_id, page_number, marker=None):
    rich_text = [{"type": "text", "text": {"content": f"📄 Page {page_number}"}}]
    if marker:
        rich_text.append({"type": "text", "text": {"content": marker}})
    return {"id": block_id, "type": "toggle", "toggle": {"rich_text": rich_text}}


def children(*blocks):
    return {"results": list(blocks), "has_more": False}


def page_item(**data):
    payload = {
        "text": "New OCR text",
        "page_number": 2,
        "page_uuid": PAGE_UUID,
        "notebook_uuid": "nb-1",
        "notebook_name": "Notebook",
        "existing_block_id": None,
        "existing_notebook_page_id": "parent-1",
    }
    payload.update(data)
    return SyncItem(
        item_type=SyncItemType.PAGE_TEXT,
        item_id="page-1",
        content_hash="hash-1",
        data=payload,
        source_table="pages",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )


@pytest.fixture
def notion():
    """(target, client) with the Notion SDK client mocked."""
    with patch("app.integrations.notion_sync.NotionClient") as mock_class:
        client = MagicMock()
        client.blocks.children.append.return_value = {"results": [{"id": "new-block"}]}
        client.blocks.children.list.return_value = children(heading())
        client.search.return_value = {"results": []}
        mock_class.return_value = client
        from app.integrations.notion_sync import NotionSyncTarget

        yield NotionSyncTarget(access_token="test-token", database_id="db-123"), client


class TestNotebookLookupFailures:
    """find_existing_page: None only on a confirmed miss, typed errors otherwise."""

    @pytest.mark.asyncio
    async def test_rate_limited_lookup_creates_nothing_and_sets_retry_after(self, notion):
        target, client = notion
        with patch("app.integrations.notion_sync.httpx.post",
                   return_value=query_response(429, headers={"Retry-After": "120"}, code="rate_limited")):
            before = datetime.utcnow()
            result = await target.sync_item(page_item(existing_notebook_page_id=None))

        assert result.status == SyncStatus.RETRY
        assert result.error_kind == SyncErrorKind.RATE_LIMITED
        assert before + timedelta(seconds=115) < result.retry_after < before + timedelta(seconds=125)
        client.pages.create.assert_not_called()
        client.blocks.children.append.assert_not_called()

    @pytest.mark.asyncio
    async def test_rate_limit_without_retry_after_defaults_to_30s(self, notion):
        target, client = notion
        with patch("app.integrations.notion_sync.httpx.post", return_value=query_response(429)):
            before = datetime.utcnow()
            result = await target.sync_item(page_item(existing_notebook_page_id=None))

        assert result.error_kind == SyncErrorKind.RATE_LIMITED
        assert before + timedelta(seconds=29) < result.retry_after < before + timedelta(seconds=35)
        client.pages.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_network_error_on_lookup_is_transient_not_a_miss(self, notion):
        target, client = notion
        with patch("app.integrations.notion_sync.httpx.post",
                   side_effect=httpx.ConnectError("connection reset")):
            result = await target.sync_item(page_item(existing_notebook_page_id=None))

        assert result.status == SyncStatus.RETRY
        assert result.error_kind == SyncErrorKind.TRANSIENT
        client.pages.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_failed_title_search_is_not_a_miss(self, notion):
        target, client = notion
        client.search.side_effect = api_error(503, "service_unavailable")
        with patch("app.integrations.notion_sync.httpx.post", return_value=query_response(200)):
            result = await target.sync_item(page_item(existing_notebook_page_id=None))

        assert result.error_kind == SyncErrorKind.TRANSIENT
        client.pages.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_rate_limited_search_raises_typed_error(self, notion):
        from app.integrations.notion_sync import NotionSyncError

        target, client = notion
        client.search.side_effect = api_error(429, "rate_limited", headers={"Retry-After": "7"})
        with patch("app.integrations.notion_sync.httpx.post", return_value=query_response(200)):
            with pytest.raises(NotionSyncError) as exc_info:
                await target.find_existing_page("nb-1")

        assert exc_info.value.kind == SyncErrorKind.RATE_LIMITED

    @pytest.mark.asyncio
    async def test_unauthorized_lookup_is_auth(self, notion):
        target, client = notion
        with patch("app.integrations.notion_sync.httpx.post",
                   return_value=query_response(401, code="unauthorized")):
            result = await target.sync_item(page_item(existing_notebook_page_id=None))

        assert result.status == SyncStatus.FAILED
        assert result.error_kind == SyncErrorKind.AUTH
        client.pages.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_confirmed_miss_returns_none(self, notion):
        target, client = notion
        # An archived page in the results does not count as a match.
        with patch("app.integrations.notion_sync.httpx.post",
                   return_value=query_response(200, results=[{"id": "old", "archived": True}])):
            assert await target.find_existing_page("nb-1") is None
        client.search.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_failure_is_typed(self, notion):
        target, client = notion
        client.pages.create.side_effect = api_error(502, "internal_server_error")
        with patch("app.integrations.notion_sync.httpx.post", return_value=query_response(200)):
            result = await target.sync_item(page_item(existing_notebook_page_id=None))

        assert result.error_kind == SyncErrorKind.TRANSIENT
        client.blocks.children.append.assert_not_called()


class TestPageUpdateOrder:
    """Append the new toggle first, delete the old one only afterwards."""

    @pytest.mark.asyncio
    async def test_append_happens_before_delete(self, notion):
        target, client = notion
        client.blocks.children.list.return_value = children(heading(), toggle("old-block", 2))
        calls = MagicMock()
        calls.attach_mock(client.blocks.children.append, "append")
        calls.attach_mock(client.blocks.delete, "delete")

        result = await target.sync_item(page_item(existing_block_id="old-block"))

        assert result.status == SyncStatus.SUCCESS
        assert result.target_id == "new-block"
        assert result.metadata["action"] == "page_updated"
        assert result.metadata["stale_block_ids"] == []
        assert [c[0] for c in calls.mock_calls] == ["append", "delete"]
        # Inserted where the old block was (after its previous sibling).
        assert client.blocks.children.append.call_args.kwargs["after"] == "heading"
        client.blocks.delete.assert_called_once_with(block_id="old-block")

    @pytest.mark.asyncio
    async def test_failed_append_leaves_old_block(self, notion):
        target, client = notion
        client.blocks.children.list.return_value = children(heading(), toggle("old-block", 2))
        client.blocks.children.append.side_effect = api_error(500, "internal_server_error")

        result = await target.sync_item(page_item(existing_block_id="old-block"))

        assert result.status == SyncStatus.RETRY
        assert result.error_kind == SyncErrorKind.TRANSIENT
        client.blocks.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_rate_limited_append_leaves_old_block(self, notion):
        target, client = notion
        client.blocks.children.list.return_value = children(heading(), toggle("old-block", 2))
        client.blocks.children.append.side_effect = api_error(
            429, "rate_limited", headers={"Retry-After": "12"}
        )

        result = await target.sync_item(page_item(existing_block_id="old-block"))

        assert result.error_kind == SyncErrorKind.RATE_LIMITED
        assert result.retry_after > datetime.utcnow() + timedelta(seconds=5)
        client.blocks.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_failed_delete_after_append_is_success_and_remembered(self, notion):
        target, client = notion
        client.blocks.children.list.return_value = children(heading(), toggle("old-block", 2))
        client.blocks.delete.side_effect = api_error(409, "conflict_error")

        result = await target.sync_item(page_item(existing_block_id="old-block"))

        assert result.status == SyncStatus.SUCCESS
        assert result.target_id == "new-block"
        assert result.metadata["stale_block_ids"] == ["old-block"]

    @pytest.mark.asyncio
    async def test_archived_old_block_counts_as_deleted(self, notion):
        target, client = notion
        client.blocks.children.list.return_value = children(heading(), toggle("old-block", 2))
        client.blocks.delete.side_effect = api_error(
            400, "validation_error", "Can't edit block that is archived."
        )

        result = await target.sync_item(page_item(existing_block_id="old-block"))

        assert result.status == SyncStatus.SUCCESS
        assert result.metadata["stale_block_ids"] == []

    @pytest.mark.asyncio
    async def test_stale_blocks_are_deleted_on_next_sync(self, notion):
        target, client = notion
        client.blocks.children.list.return_value = children(
            heading(), toggle("current-block", 2), toggle("stale-block", 2)
        )

        result = await target.sync_item(
            page_item(existing_block_id="current-block", stale_block_ids=["stale-block"])
        )

        assert result.status == SyncStatus.SUCCESS
        assert result.metadata["stale_block_ids"] == []
        deleted = [c.kwargs["block_id"] for c in client.blocks.delete.call_args_list]
        assert deleted == ["stale-block", "current-block"]

    @pytest.mark.asyncio
    async def test_stale_block_kept_while_delete_keeps_failing(self, notion):
        target, client = notion
        client.blocks.children.list.return_value = children(heading(), toggle("current-block", 2))

        def delete(block_id):
            if block_id == "stale-block":
                raise api_error(503, "service_unavailable")
            return {}

        client.blocks.delete.side_effect = delete
        result = await target.sync_item(
            page_item(existing_block_id="current-block", stale_block_ids=["stale-block"])
        )

        assert result.status == SyncStatus.SUCCESS
        assert result.metadata["stale_block_ids"] == ["stale-block"]

    @pytest.mark.asyncio
    async def test_never_deletes_the_notebook_page_as_a_block(self, notion):
        target, client = notion
        result = await target.sync_item(page_item(stale_block_ids=["parent-1"]))

        assert result.status == SyncStatus.SUCCESS
        client.blocks.delete.assert_not_called()


class TestDuplicateToggleAdoption:
    """A toggle appended by an attempt that was never recorded is replaced."""

    @pytest.mark.asyncio
    async def test_new_toggle_carries_page_marker(self, notion):
        target, client = notion
        await target.sync_item(page_item())

        rich_text = client.blocks.children.append.call_args.kwargs["children"][0]["toggle"]["rich_text"]
        assert rich_text[0]["text"]["content"] == "📄 Page 2"
        assert rich_text[1]["text"]["content"] == MARKER
        assert rich_text[1]["annotations"] == {"color": "gray"}

    @pytest.mark.asyncio
    async def test_marked_orphan_is_replaced_not_duplicated(self, notion):
        target, client = notion
        client.blocks.children.list.return_value = children(
            heading(), toggle("page-3", 3), toggle("orphan", 2, MARKER), toggle("page-1", 1)
        )

        result = await target.sync_item(page_item())

        assert result.status == SyncStatus.SUCCESS
        assert result.metadata["action"] == "page_adopted"
        client.blocks.children.append.assert_called_once()
        assert client.blocks.children.append.call_args.kwargs["after"] == "page-3"
        client.blocks.delete.assert_called_once_with(block_id="orphan")

    @pytest.mark.asyncio
    async def test_orphan_from_crashed_update_is_removed_too(self, notion):
        target, client = notion
        client.blocks.children.list.return_value = children(
            heading(), toggle("orphan", 2, MARKER), toggle("recorded", 2, MARKER)
        )

        result = await target.sync_item(page_item(existing_block_id="recorded"))

        assert result.status == SyncStatus.SUCCESS
        deleted = sorted(c.kwargs["block_id"] for c in client.blocks.delete.call_args_list)
        assert deleted == ["orphan", "recorded"]

    @pytest.mark.asyncio
    async def test_unmarked_legacy_toggle_matched_by_exact_title(self, notion):
        target, client = notion
        client.blocks.children.list.return_value = children(
            heading(), toggle("legacy", 2), toggle("legacy-dup", 2)
        )

        result = await target.sync_item(page_item())

        assert result.metadata["action"] == "page_adopted"
        client.blocks.delete.assert_called_once_with(block_id="legacy")

    @pytest.mark.asyncio
    async def test_toggles_of_other_pages_are_never_adopted(self, notion):
        target, client = notion
        client.blocks.children.list.return_value = children(
            heading(),
            toggle("other-page", 2, " · ccccdddd"),  # another page's marker
            toggle("claimed-legacy", 2),  # recorded for another page
        )

        result = await target.sync_item(page_item(claimed_block_ids=["claimed-legacy"]))

        assert result.metadata["action"] == "page_created"
        client.blocks.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_title_fallback_not_used_for_recorded_page(self, notion):
        target, client = notion
        client.blocks.children.list.return_value = children(heading(), toggle("legacy", 2))

        result = await target.sync_item(page_item(existing_block_id="gone-block"))

        assert result.status == SyncStatus.SUCCESS
        client.blocks.delete.assert_not_called()


class TestParentGone:
    """The notebook's Notion page was archived or deleted."""

    @pytest.mark.asyncio
    async def test_archived_parent_on_append(self, notion):
        target, client = notion
        client.blocks.children.append.side_effect = api_error(
            400, "validation_error", "Can't edit block that is archived."
        )
        client.pages.retrieve.return_value = {"id": "parent-1", "archived": True}

        result = await target.sync_item(page_item())

        assert result.status == SyncStatus.RETRY
        assert result.error_kind == SyncErrorKind.PARENT_GONE
        client.pages.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_missing_parent_on_list(self, notion):
        target, client = notion
        client.blocks.children.list.side_effect = api_error(404, "object_not_found")
        client.pages.retrieve.side_effect = api_error(404, "object_not_found")

        result = await target.sync_item(page_item())

        assert result.error_kind == SyncErrorKind.PARENT_GONE
        client.blocks.children.append.assert_not_called()

    @pytest.mark.asyncio
    async def test_archived_anchor_with_live_parent_is_transient(self, notion):
        target, client = notion
        client.blocks.children.append.side_effect = api_error(
            400, "validation_error", "Can't edit block that is archived."
        )
        client.pages.retrieve.return_value = {"id": "parent-1", "archived": False, "in_trash": False}

        result = await target.sync_item(page_item())

        assert result.error_kind == SyncErrorKind.TRANSIENT


class TestErrorClassification:
    @pytest.mark.parametrize(
        "status,code,kind",
        [
            (429, "rate_limited", SyncErrorKind.RATE_LIMITED),
            (401, "unauthorized", SyncErrorKind.AUTH),
            (403, "restricted_resource", SyncErrorKind.AUTH),
            (500, "internal_server_error", SyncErrorKind.TRANSIENT),
            (503, "service_unavailable", SyncErrorKind.TRANSIENT),
            (409, "conflict_error", SyncErrorKind.TRANSIENT),
            (400, "validation_error", SyncErrorKind.PERMANENT),
            (404, "object_not_found", SyncErrorKind.PERMANENT),
        ],
    )
    def test_api_error_codes(self, status, code, kind):
        from app.integrations.notion_sync import classify_notion_error

        assert classify_notion_error(api_error(status, code)).kind == kind

    def test_unknown_exception_is_unclassified(self):
        from app.integrations.notion_sync import classify_notion_error

        assert classify_notion_error(ValueError("boom")) is None

    def test_retry_after_http_date(self):
        from app.integrations.notion_sync import _retry_after_from_headers

        when = datetime.utcnow() + timedelta(seconds=90)
        header = when.strftime("%a, %d %b %Y %H:%M:%S GMT")
        retry_at = _retry_after_from_headers({"Retry-After": header})
        assert abs((retry_at - when).total_seconds()) < 2
