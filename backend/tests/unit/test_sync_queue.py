"""Integration tests for services/sync_queue.py.

Tests queue creation, deduplication by page_uuid and content_hash,
page/todo routing, and priority ordering.
"""

from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

import pytest
from sqlalchemy.orm import Session

from app.models.sync_record import IntegrationConfig, SyncQueue, SyncRecord
from tests.conftest import create_user_with_quota


@pytest.fixture
def user(db: Session):
    """Create a test user."""
    return create_user_with_quota(db, used=0, limit=30)


@pytest.fixture
def notebook(db: Session, user):
    """Create a test notebook for the user."""
    from app.models.notebook import Notebook
    nb = Notebook(
        notebook_uuid="nb-test-uuid",
        user_id=user.id,
        visible_name="Test Notebook",
        document_type="notebook",
        created_at=datetime.utcnow(),
    )
    db.add(nb)
    db.commit()
    db.refresh(nb)
    return nb


@pytest.fixture
def notion_integration(db: Session, user):
    """Create an enabled Notion integration config (unencrypted for test)."""
    config = IntegrationConfig(
        user_id=user.id,
        target_name="notion",
        is_enabled=True,
        config_encrypted='{"access_token": "test", "database_id": "db-1"}',
    )
    db.add(config)
    db.commit()
    db.refresh(config)
    return config


@pytest.fixture
def notion_todos_integration(db: Session, user):
    """Create an enabled Notion-todos integration config."""
    config = IntegrationConfig(
        user_id=user.id,
        target_name="notion-todos",
        is_enabled=True,
        config_encrypted='{"access_token": "test", "database_id": "db-2"}',
    )
    db.add(config)
    db.commit()
    db.refresh(config)
    return config


class TestQueueSync:
    """Tests for the queue_sync function."""

    def test_queue_sync_creates_entry(self, db, user):
        """queue_sync should create a new pending SyncQueue entry."""
        from app.services.sync_queue import queue_sync

        entry = queue_sync(
            db=db,
            user_id=user.id,
            item_type="page_text",
            item_id="1",
            content_hash="hash123",
            target_name="notion",
            page_uuid="page-uuid-1",
            notebook_uuid="nb-uuid-1",
            page_number=1,
        )
        assert entry.id is not None
        assert entry.status == "pending"
        assert entry.content_hash == "hash123"
        assert entry.page_uuid == "page-uuid-1"

    def test_queue_sync_dedup_by_page_uuid(self, db, user):
        """Same page_uuid with same content should return existing entry."""
        from app.services.sync_queue import queue_sync

        entry1 = queue_sync(
            db=db,
            user_id=user.id,
            item_type="page_text",
            item_id="1",
            content_hash="hash123",
            target_name="notion",
            page_uuid="page-uuid-dedup",
        )
        entry2 = queue_sync(
            db=db,
            user_id=user.id,
            item_type="page_text",
            item_id="1",
            content_hash="hash123",
            target_name="notion",
            page_uuid="page-uuid-dedup",
        )
        assert entry1.id == entry2.id

    def test_queue_sync_updates_hash_on_change(self, db, user):
        """Same page_uuid with changed content should update the hash."""
        from app.services.sync_queue import queue_sync

        entry1 = queue_sync(
            db=db,
            user_id=user.id,
            item_type="page_text",
            item_id="1",
            content_hash="old_hash",
            target_name="notion",
            page_uuid="page-uuid-update",
        )
        entry2 = queue_sync(
            db=db,
            user_id=user.id,
            item_type="page_text",
            item_id="1",
            content_hash="new_hash",
            target_name="notion",
            page_uuid="page-uuid-update",
        )
        assert entry1.id == entry2.id
        # Refresh to see the update
        db.refresh(entry1)
        assert entry1.content_hash == "new_hash"

    def test_queue_sync_skips_already_synced(self, db, user):
        """If already synced with same content_hash, return completed entry."""
        from app.services.sync_queue import queue_sync

        # Create a successful sync record
        sync_record = SyncRecord(
            user_id=user.id,
            target_name="notion",
            item_type="page_text",
            item_id="1",
            content_hash="synced_hash",
            external_id="ext-123",
            status="success",
            page_uuid="page-uuid-synced",
            synced_at=datetime.utcnow(),
        )
        db.add(sync_record)
        db.commit()

        entry = queue_sync(
            db=db,
            user_id=user.id,
            item_type="page_text",
            item_id="1",
            content_hash="synced_hash",
            target_name="notion",
            page_uuid="page-uuid-synced",
        )
        assert entry.status == "completed"

    def test_queue_sync_dedup_by_content_hash_for_non_page(self, db, user):
        """Non-page_text items should dedup by content_hash."""
        from app.services.sync_queue import queue_sync

        entry1 = queue_sync(
            db=db,
            user_id=user.id,
            item_type="todo",
            item_id="1",
            content_hash="todo_hash",
            target_name="notion-todos",
        )
        entry2 = queue_sync(
            db=db,
            user_id=user.id,
            item_type="todo",
            item_id="2",
            content_hash="todo_hash",
            target_name="notion-todos",
        )
        assert entry1.id == entry2.id


class TestQueuePageSync:
    """Tests for queue_page_sync routing."""

    def test_queues_to_enabled_integrations(self, db, user, notion_integration):
        """queue_page_sync should create entries for enabled integrations."""
        from app.services.sync_queue import queue_page_sync

        entries = queue_page_sync(
            db=db,
            user_id=user.id,
            page_id=1,
            notebook_uuid="nb-uuid",
            page_number=1,
            ocr_text="Test OCR text",
            page_uuid="page-uuid-1",
        )
        assert len(entries) == 1
        assert entries[0].target_name == "notion"

    def test_excludes_todo_only_integrations(self, db, user, notion_integration, notion_todos_integration):
        """queue_page_sync should not queue to todo-only integrations."""
        from app.services.sync_queue import queue_page_sync

        entries = queue_page_sync(
            db=db,
            user_id=user.id,
            page_id=1,
            notebook_uuid="nb-uuid",
            page_number=1,
            ocr_text="Test OCR text",
        )
        target_names = [e.target_name for e in entries]
        assert "notion" in target_names
        assert "notion-todos" not in target_names

    def test_returns_empty_when_no_integrations(self, db, user):
        """queue_page_sync should return empty list with no enabled integrations."""
        from app.services.sync_queue import queue_page_sync

        entries = queue_page_sync(
            db=db,
            user_id=user.id,
            page_id=1,
            notebook_uuid="nb-uuid",
            page_number=1,
            ocr_text="Test OCR text",
        )
        assert entries == []


class TestQueueTodoSync:
    """Tests for queue_todo_sync routing."""

    def test_queues_to_todo_integrations(self, db, user, notion_todos_integration):
        """queue_todo_sync should queue to todo-specific integrations."""
        from app.services.sync_queue import queue_todo_sync

        entries = queue_todo_sync(
            db=db,
            user_id=user.id,
            todo_id=1,
            todo_text="Buy groceries",
            notebook_uuid="nb-uuid",
            page_number=1,
        )
        assert len(entries) == 1
        assert entries[0].target_name == "notion-todos"

    def test_excludes_notebook_integrations(self, db, user, notion_integration, notion_todos_integration):
        """queue_todo_sync should not queue to general notebook integrations."""
        from app.services.sync_queue import queue_todo_sync

        entries = queue_todo_sync(
            db=db,
            user_id=user.id,
            todo_id=1,
            todo_text="Buy groceries",
            notebook_uuid="nb-uuid",
        )
        target_names = [e.target_name for e in entries]
        assert "notion-todos" in target_names
        assert "notion" not in target_names


class TestGetNextSyncItems:
    """Tests for get_next_sync_items ordering."""

    def test_ordered_by_priority_then_created_at(self, db, user):
        """Items should be returned by priority (ascending) then creation time."""
        from app.services.sync_queue import get_next_sync_items

        now = datetime.utcnow()

        # Create items: low priority first, then high priority
        low_prio = SyncQueue(
            user_id=user.id,
            item_type="page_text",
            item_id="1",
            content_hash="h1",
            target_name="notion",
            status="pending",
            priority=5,
            scheduled_at=now - timedelta(minutes=5),
            created_at=now - timedelta(minutes=5),
        )
        high_prio = SyncQueue(
            user_id=user.id,
            item_type="page_text",
            item_id="2",
            content_hash="h2",
            target_name="notion",
            status="pending",
            priority=1,
            scheduled_at=now - timedelta(minutes=1),
            created_at=now - timedelta(minutes=1),
        )
        db.add_all([low_prio, high_prio])
        db.commit()

        items = get_next_sync_items(db, limit=10)
        assert len(items) == 2
        assert items[0].priority == 1  # Higher priority (lower number) first
        assert items[1].priority == 5

    def test_skips_future_scheduled_items(self, db, user):
        """Items scheduled in the future should not be returned."""
        from app.services.sync_queue import get_next_sync_items

        now = datetime.utcnow()

        ready = SyncQueue(
            user_id=user.id,
            item_type="page_text",
            item_id="1",
            content_hash="h1",
            target_name="notion",
            status="pending",
            priority=5,
            scheduled_at=now - timedelta(minutes=1),
            created_at=now - timedelta(minutes=1),
        )
        future = SyncQueue(
            user_id=user.id,
            item_type="page_text",
            item_id="2",
            content_hash="h2",
            target_name="notion",
            status="pending",
            priority=5,
            scheduled_at=now + timedelta(hours=1),
            created_at=now,
        )
        db.add_all([ready, future])
        db.commit()

        items = get_next_sync_items(db, limit=10)
        assert len(items) == 1
        assert items[0].item_id == "1"
