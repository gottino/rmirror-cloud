"""Tests for sync worker todo item dispatch."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.notebook import Notebook
from app.models.sync_record import IntegrationConfig, SyncQueue
from app.models.todo import Todo
from app.services.sync_worker import SyncWorker


@pytest.fixture
def worker():
    return SyncWorker(poll_interval=1)


def _make_queue_item(target_name="todoist"):
    item = MagicMock(spec=SyncQueue)
    item.id = 1
    item.user_id = 1
    item.item_type = "todo"
    item.item_id = "42"
    item.content_hash = "abc123"
    item.target_name = target_name
    item.page_uuid = None
    item.notebook_uuid = "nb-uuid"
    item.page_number = 3
    item.metadata_json = None
    item.retry_count = 0
    item.status = "processing"
    return item


def _make_todo():
    todo = MagicMock(spec=Todo)
    todo.id = 42
    todo.text = "Buy milk"
    todo.title = "Buy milk"
    todo.completed = False
    todo.page_number = 3
    todo.page_uuid = "page-uuid-1"
    todo.notebook_id = 10
    todo.confidence = 0.95
    todo.date_extracted = None
    todo.created_at = datetime.utcnow()
    todo.updated_at = datetime.utcnow()
    return todo


def _make_notebook():
    nb = MagicMock(spec=Notebook)
    nb.id = 10
    nb.visible_name = "Shopping List"
    nb.notebook_uuid = "nb-uuid"
    return nb


def _make_config():
    config = MagicMock(spec=IntegrationConfig)
    config.get_config.return_value = {
        "access_token": "test_token",
        "project_id": "proj_123",
        "project_name": "reMarkable Notes",
    }
    return config


class TestProcessTodoSync:
    @pytest.mark.asyncio
    async def test_dispatches_to_todoist(self, worker):
        db = MagicMock()
        queue_item = _make_queue_item(target_name="todoist")
        config = _make_config()
        todo = _make_todo()
        notebook = _make_notebook()

        # Mock DB queries: Todo, Notebook, existing SyncRecord
        db.query.return_value.filter.return_value.first.side_effect = [
            todo,       # Todo query
            notebook,   # Notebook query
            None,       # Existing SyncRecord query
        ]

        with patch("app.services.sync_worker.TodoistSyncTarget") as mock_target_class:
            mock_target = AsyncMock()
            mock_target.sync_item = AsyncMock(return_value=MagicMock(
                success=True,
                target_id="task_999",
                metadata={},
            ))
            mock_target_class.return_value = mock_target

            await worker._process_todo_sync(db, queue_item, config)

        assert queue_item.status == "completed"
        mock_target.sync_item.assert_called_once()

    @pytest.mark.asyncio
    async def test_dispatches_to_notion_todos(self, worker):
        db = MagicMock()
        queue_item = _make_queue_item(target_name="notion-todos")
        config = MagicMock(spec=IntegrationConfig)
        config.get_config.return_value = {
            "access_token": "test_token",
            "database_id": "db_123",
            "use_status_property": False,
        }
        todo = _make_todo()
        notebook = _make_notebook()

        db.query.return_value.filter.return_value.first.side_effect = [
            todo,
            notebook,
            None,
        ]

        with patch("app.services.sync_worker.NotionTodosSyncTarget") as mock_target_class:
            mock_target = AsyncMock()
            mock_target.sync_item = AsyncMock(return_value=MagicMock(
                success=True,
                target_id="page_123",
                metadata={},
            ))
            mock_target_class.return_value = mock_target

            await worker._process_todo_sync(db, queue_item, config)

        assert queue_item.status == "completed"

    @pytest.mark.asyncio
    async def test_fails_when_todo_not_found(self, worker):
        db = MagicMock()
        queue_item = _make_queue_item()
        config = _make_config()

        db.query.return_value.filter.return_value.first.return_value = None

        await worker._process_todo_sync(db, queue_item, config)
        assert queue_item.status == "failed"
        assert "not found" in queue_item.error_message.lower()
