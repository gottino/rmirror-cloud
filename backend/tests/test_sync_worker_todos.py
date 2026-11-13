"""Tests for the sync worker's todo items (Todoist, Notion todos).

Uses the SQLite test database; only the target is faked, through the target
registry (``app.integrations.registry.<TargetClass>``).
"""

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.sync_engine import SyncResult
from app.models.notebook import Notebook
from app.models.sync_record import IntegrationConfig, SyncQueue, SyncRecord, SyncStatus
from app.models.todo import REMOVED_FROM_PAGE, Todo
from app.services.sync_queue import queue_todo_sync
from app.services.sync_worker import SyncWorker
from tests.conftest import create_user_with_quota

TARGET_CLASSES = {
    "todoist": "app.integrations.registry.TodoistSyncTarget",
    "notion-todos": "app.integrations.registry.NotionTodosSyncTarget",
}


@pytest.fixture
def worker():
    return SyncWorker(poll_interval=1)


@pytest.fixture
def setup(db):
    user = create_user_with_quota(db, email="todos-worker@example.com")
    notebook = Notebook(
        notebook_uuid="nb-uuid",
        user_id=user.id,
        visible_name="Shopping List",
        document_type="notebook",
    )
    db.add(notebook)
    db.commit()
    for target in ("todoist", "notion-todos"):
        db.add(
            IntegrationConfig(
                user_id=user.id, target_name=target, is_enabled=True, config_encrypted="x"
            )
        )
    todo = Todo(
        user_id=user.id,
        notebook_id=notebook.id,
        page_number=3,
        title="Buy milk",
        text="Buy milk",
        completed=False,
        confidence=0.95,
    )
    db.add(todo)
    db.commit()
    return user, notebook, todo


def _fake_target(target_id="ext_1"):
    target = MagicMock()
    ok = SyncResult(status=SyncStatus.SUCCESS, target_id=target_id)
    target.sync_item = AsyncMock(return_value=ok)
    target.update_item = AsyncMock(return_value=ok)
    return target


async def _run(worker, db, target_name, fake):
    """Let the worker process the pending todo row of ``target_name``."""
    row = (
        db.query(SyncQueue)
        .filter_by(target_name=target_name, item_type="todo", status="pending")
        .one()
    )
    config = db.query(IntegrationConfig).filter_by(target_name=target_name).one()
    with patch(TARGET_CLASSES[target_name], return_value=fake), patch.object(
        IntegrationConfig, "get_config", return_value={"access_token": "t"}
    ):
        await worker._process_todo_sync(db, row, config)
    return row


def _record(db, target_name):
    return db.query(SyncRecord).filter_by(item_type="todo", target_name=target_name).one()


class TestProcessTodoSync:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("target_name", ["todoist", "notion-todos"])
    async def test_creates_once_and_records_it(self, worker, db, setup, target_name):
        _, _, todo = setup
        queue_todo_sync(db, todo, "nb-uuid")
        fake = _fake_target()

        row = await _run(worker, db, target_name, fake)

        assert row.status == "completed"
        fake.sync_item.assert_awaited_once()
        item = fake.sync_item.await_args.args[0]
        assert item.data["text"] == "Buy milk"
        assert item.data["completed"] is False
        assert item.data["notebook_name"] == "Shopping List"
        record = _record(db, target_name)
        assert record.external_id == "ext_1"
        assert json.loads(record.metadata_json) == {"completed": False}

        # Nothing changed: this target gets nothing queued again.
        queue_todo_sync(db, todo, "nb-uuid")
        assert db.query(SyncQueue).filter_by(target_name=target_name).count() == 1

    @pytest.mark.asyncio
    @pytest.mark.parametrize("target_name", ["todoist", "notion-todos"])
    async def test_checked_later_updates_with_completed(self, worker, db, setup, target_name):
        _, _, todo = setup
        queue_todo_sync(db, todo, "nb-uuid", [target_name])
        await _run(worker, db, target_name, _fake_target())

        todo.completed = True
        db.commit()
        assert len(queue_todo_sync(db, todo, "nb-uuid", [target_name])) == 1
        fake = _fake_target()
        await _run(worker, db, target_name, fake)

        fake.sync_item.assert_not_awaited()
        external_id, item = fake.update_item.await_args.args
        assert external_id == "ext_1"
        assert item.data["completed"] is True
        assert item.data["previous_completed"] is False
        assert json.loads(_record(db, target_name).metadata_json) == {"completed": True}

    @pytest.mark.asyncio
    async def test_partial_create_is_recorded_so_retry_updates(self, worker, db, setup):
        """Created but not closed: the task id is kept, the retry updates (no 2nd task)."""
        _, _, todo = setup
        todo.completed = True
        db.commit()
        queue_todo_sync(db, todo, "nb-uuid", ["todoist"])
        fake = _fake_target()
        fake.sync_item = AsyncMock(
            return_value=SyncResult(
                status=SyncStatus.RETRY, target_id="task_9", error_message="close failed"
            )
        )

        row = await _run(worker, db, "todoist", fake)
        assert row.status == "pending" and row.retry_count == 1
        record = _record(db, "todoist")
        assert record.external_id == "task_9"
        assert json.loads(record.metadata_json) == {"completed": False}

        row.scheduled_at = datetime.utcnow()
        db.commit()
        retry = _fake_target("task_9")
        await _run(worker, db, "todoist", retry)
        retry.sync_item.assert_not_awaited()
        external_id, item = retry.update_item.await_args.args
        assert external_id == "task_9"
        assert item.data["completed"] is True and item.data["previous_completed"] is False

    @pytest.mark.asyncio
    async def test_removed_todo_is_not_sent(self, worker, db, setup):
        _, _, todo = setup
        queue_todo_sync(db, todo, "nb-uuid", ["todoist"])
        todo.removed_at = datetime.utcnow()
        todo.removed_reason = REMOVED_FROM_PAGE
        db.commit()
        fake = _fake_target()

        row = await _run(worker, db, "todoist", fake)

        assert row.status == "completed"
        fake.sync_item.assert_not_awaited()
        fake.update_item.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_fails_when_todo_not_found(self, worker, db, setup):
        user, _, _ = setup
        row = SyncQueue(
            user_id=user.id,
            item_type="todo",
            item_id="999999",
            content_hash="x",
            target_name="todoist",
            status="processing",
        )
        db.add(row)
        db.commit()
        config = db.query(IntegrationConfig).filter_by(target_name="todoist").one()

        await worker._process_todo_sync(db, row, config)

        assert row.status == "failed"
        assert "not found" in row.error_message.lower()
