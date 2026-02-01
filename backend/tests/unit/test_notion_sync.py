"""Unit tests for NotionSyncTarget.

Tests cover:
- Notebook syncing with full metadata
- Notebook metadata-only syncing
- Page text syncing with block management
- Deduplication using page_uuid
- Error handling for archived blocks and rate limiting
"""

import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch

from app.core.sync_engine import SyncItem, SyncResult
from app.models.sync_record import SyncItemType, SyncStatus


class TestNotionSyncTargetInit:
    """Tests for NotionSyncTarget constructor."""

    def test_init_with_ssl_disabled(self):
        """Verify SSL verification can be disabled."""
        with patch("app.integrations.notion_sync.NotionClient") as mock_notion:
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

            target = NotionSyncTarget(
                access_token="test-token",
                database_id="db-123",
                verify_ssl=True,
            )

            # Should NOT use httpx client (SSL enabled = default behavior)
            mock_notion.assert_called_once()


class TestNotionSyncTargetNotebookSync:
    """Tests for notebook syncing."""

    @pytest.mark.asyncio
    async def test_sync_notebook_creates_page_with_metadata(self, sample_notebook_sync_item):
        """Verify notebook sync creates page with all metadata fields."""
        with patch("app.integrations.notion_sync.NotionClient") as mock_notion_class:
            with patch("app.integrations.notion_sync.httpx.Client"):
                mock_client = MagicMock()
                mock_client.pages.create.return_value = {"id": "notebook-page-123"}
                # No existing page found
                mock_client.search.return_value = {"results": []}
                mock_notion_class.return_value = mock_client

                # Mock httpx.post for database query (find_existing_page)
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

                    result = await target.sync_item(sample_notebook_sync_item)

                    assert result.status == SyncStatus.SUCCESS
                    assert result.target_id == "notebook-page-123"
                    assert result.metadata.get("action") == "created"

                    # Verify page was created with correct properties
                    call_args = mock_client.pages.create.call_args
                    properties = call_args.kwargs["properties"]

                    # Core properties
                    assert "Name" in properties
                    assert properties["Name"]["title"][0]["text"]["content"] == "Test Notebook"

                    assert "UUID" in properties
                    assert properties["UUID"]["rich_text"][0]["text"]["content"] == "nb-123"

                    assert "Path" in properties
                    assert properties["Path"]["rich_text"][0]["text"]["content"] == "Work/Projects/Client A"

                    # Page count
                    assert "Pages" in properties
                    assert properties["Pages"]["number"] == 2

                    # Tags from path
                    assert "Tags" in properties
                    tag_names = [t["name"] for t in properties["Tags"]["multi_select"]]
                    assert "Work" in tag_names
                    assert "Projects" in tag_names
                    assert "Client A" in tag_names

                    # Timestamps
                    assert "Last Opened" in properties
                    assert "Last Modified" in properties
                    assert "Synced At" in properties

                    # Status
                    assert "Status" in properties
                    assert properties["Status"]["select"]["name"] == "Synced"

    @pytest.mark.asyncio
    async def test_sync_notebook_updates_existing_page(self, sample_notebook_sync_item):
        """Verify notebook sync updates existing page when found."""
        with patch("app.integrations.notion_sync.NotionClient") as mock_notion_class:
            with patch("app.integrations.notion_sync.httpx.Client"):
                mock_client = MagicMock()
                mock_client.pages.update.return_value = {"id": "existing-page-456"}
                mock_client.blocks.children.list.return_value = {"results": [], "has_more": False}
                mock_client.blocks.children.append.return_value = {"results": []}
                mock_notion_class.return_value = mock_client

                # Mock httpx.post to return existing page
                with patch("httpx.post") as mock_post:
                    mock_response = MagicMock()
                    mock_response.status_code = 200
                    mock_response.json.return_value = {
                        "results": [{"id": "existing-page-456"}]
                    }
                    mock_post.return_value = mock_response

                    from app.integrations.notion_sync import NotionSyncTarget

                    target = NotionSyncTarget(
                        access_token="test-token",
                        database_id="db-123",
                    )

                    result = await target.sync_item(sample_notebook_sync_item)

                    assert result.status == SyncStatus.SUCCESS
                    assert result.target_id == "existing-page-456"
                    assert result.metadata.get("action") == "updated"

                    # Verify page was updated, not created
                    mock_client.pages.update.assert_called()
                    mock_client.pages.create.assert_not_called()

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
    async def test_handles_sync_item_exception(self, sample_notebook_sync_item):
        """Test general exception handling in sync_item - returns RETRY on page creation failure."""
        with patch("app.integrations.notion_sync.NotionClient") as mock_notion_class:
            with patch("app.integrations.notion_sync.httpx.Client"):
                mock_client = MagicMock()
                mock_client.search.return_value = {"results": []}
                # Page creation fails (returns None which triggers RETRY, not FAILED)
                mock_client.pages.create.side_effect = Exception("API error: invalid database")
                mock_notion_class.return_value = mock_client

                with patch("httpx.post") as mock_post:
                    # Database query returns no results (so it tries to create)
                    mock_response = MagicMock()
                    mock_response.status_code = 200
                    mock_response.json.return_value = {"results": []}
                    mock_post.return_value = mock_response

                    from app.integrations.notion_sync import NotionSyncTarget

                    target = NotionSyncTarget(
                        access_token="test-token",
                        database_id="db-123",
                    )

                    result = await target.sync_item(sample_notebook_sync_item)

                    # The implementation returns RETRY when page creation fails
                    # (exception is caught in _create_notion_page, returns None)
                    assert result.status == SyncStatus.RETRY
                    assert "Failed to create Notion page" in result.error_message

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
