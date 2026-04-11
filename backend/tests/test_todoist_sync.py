"""Tests for Todoist sync target."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.sync_engine import SyncItem, SyncItemType
from app.integrations.todoist_sync import TodoistSyncTarget
from app.models.sync_record import SyncStatus


@pytest.fixture
def sync_target():
    return TodoistSyncTarget(
        access_token="test_token",
        project_id="12345",
    )


def _make_todo_item(
    text="Buy groceries",
    notebook_name="Shopping List",
    page_number=3,
    completed=False,
):
    return SyncItem(
        item_type=SyncItemType.TODO,
        item_id="1",
        content_hash="abc123",
        data={
            "text": text,
            "notebook_name": notebook_name,
            "page_number": page_number,
            "completed": completed,
            "notebook_uuid": "uuid-123",
        },
        source_table="todos",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )


class TestSyncItem:
    @pytest.mark.asyncio
    async def test_creates_todoist_task(self, sync_target):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "task_999"}

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            item = _make_todo_item()
            result = await sync_target.sync_item(item)

        assert result.success
        assert result.target_id == "task_999"

    @pytest.mark.asyncio
    async def test_includes_labels(self, sync_target):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "task_999"}

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            item = _make_todo_item(notebook_name="Work Notes")
            await sync_target.sync_item(item)

            call_kwargs = mock_client.post.call_args
            payload = call_kwargs.kwargs.get("json", {})
            assert "remarkable" in payload["labels"]
            assert "Work Notes" in payload["labels"]

    @pytest.mark.asyncio
    async def test_includes_description_with_source(self, sync_target):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "task_999"}

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            item = _make_todo_item(notebook_name="Meeting Notes", page_number=5)
            await sync_target.sync_item(item)

            call_kwargs = mock_client.post.call_args
            payload = call_kwargs.kwargs.get("json", {})
            assert "Meeting Notes" in payload["description"]
            assert "5" in payload["description"]

    @pytest.mark.asyncio
    async def test_skips_non_todo_items(self, sync_target):
        item = SyncItem(
            item_type=SyncItemType.PAGE_TEXT,
            item_id="1",
            content_hash="abc",
            data={},
            source_table="pages",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        result = await sync_target.sync_item(item)
        assert result.status == SyncStatus.SKIPPED

    @pytest.mark.asyncio
    async def test_skips_empty_text(self, sync_target):
        item = _make_todo_item(text="")
        result = await sync_target.sync_item(item)
        assert result.status == SyncStatus.SKIPPED

    @pytest.mark.asyncio
    async def test_handles_rate_limit(self, sync_target):
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.headers = {"Retry-After": "30"}

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            item = _make_todo_item()
            result = await sync_target.sync_item(item)

        assert result.status == SyncStatus.RETRY


class TestUpdateItem:
    @pytest.mark.asyncio
    async def test_updates_existing_task(self, sync_target):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "task_999"}

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            item = _make_todo_item(text="Updated task")
            result = await sync_target.update_item("task_999", item)

        assert result.success


class TestDeleteItem:
    @pytest.mark.asyncio
    async def test_deletes_task(self, sync_target):
        mock_response = MagicMock()
        mock_response.status_code = 204

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.delete = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            result = await sync_target.delete_item("task_999")

        assert result.success
