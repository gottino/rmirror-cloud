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
        """If already synced with same content_hash, queue nothing and write no row."""
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
        assert entry is None
        assert db.query(SyncQueue).count() == 0

    def test_queue_sync_inserts_new_pending_row_when_existing_is_processing(self, db, user):
        """An in-flight row keeps its content; new content gets a new pending row."""
        from app.services.sync_queue import queue_sync

        inflight = queue_sync(
            db=db, user_id=user.id, item_type="page_text", item_id="1",
            content_hash="old_hash", target_name="notion", page_uuid="page-uuid-inflight",
        )
        inflight.status = "processing"
        inflight.started_at = datetime.utcnow()
        db.commit()

        fresh = queue_sync(
            db=db, user_id=user.id, item_type="page_text", item_id="1",
            content_hash="new_hash", target_name="notion", page_uuid="page-uuid-inflight",
        )

        assert fresh.id != inflight.id
        assert fresh.status == "pending"
        assert fresh.content_hash == "new_hash"
        db.refresh(inflight)
        assert inflight.status == "processing"
        assert inflight.content_hash == "old_hash"

    def test_queue_sync_dedup_by_content_hash_for_other_types(self, db, user):
        """Item types without their own rule (highlight) dedup by content_hash."""
        from app.services.sync_queue import queue_sync

        entry1 = queue_sync(
            db=db,
            user_id=user.id,
            item_type="highlight",
            item_id="1",
            content_hash="hl_hash",
            target_name="readwise",
        )
        entry2 = queue_sync(
            db=db,
            user_id=user.id,
            item_type="highlight",
            item_id="2",
            content_hash="hl_hash",
            target_name="readwise",
        )
        assert entry1.id == entry2.id

    def test_queue_sync_todos_are_deduplicated_per_todo(self, db, user):
        """Two todos with the same hash are two items; one todo has one pending row."""
        from app.services.sync_queue import queue_sync

        def q(item_id, content_hash):
            return queue_sync(
                db=db,
                user_id=user.id,
                item_type="todo",
                item_id=item_id,
                content_hash=content_hash,
                target_name="notion-todos",
            )

        first = q("1", "todo_hash")
        assert q("2", "todo_hash").id != first.id
        again = q("1", "new_hash")
        assert again.id == first.id and again.content_hash == "new_hash"


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


def _todo(db, user, notebook, text="Buy groceries", completed=False):
    from app.models.todo import Todo

    todo = Todo(
        user_id=user.id,
        notebook_id=notebook.id,
        page_number=1,
        title=text,
        text=text,
        completed=completed,
    )
    db.add(todo)
    db.commit()
    return todo


class TestQueueTodoSync:
    """Tests for queue_todo_sync routing and per-todo de-duplication."""

    def test_queues_to_todo_integrations(self, db, user, notebook, notion_todos_integration):
        """queue_todo_sync should queue to todo-specific integrations."""
        from app.services.sync_queue import queue_todo_sync

        entries = queue_todo_sync(db, _todo(db, user, notebook), "nb-uuid")
        assert len(entries) == 1
        assert entries[0].target_name == "notion-todos"

    def test_excludes_notebook_integrations(
        self, db, user, notebook, notion_integration, notion_todos_integration
    ):
        """queue_todo_sync should not queue to general notebook integrations."""
        from app.services.sync_queue import queue_todo_sync

        entries = queue_todo_sync(db, _todo(db, user, notebook), "nb-uuid")
        target_names = [e.target_name for e in entries]
        assert "notion-todos" in target_names
        assert "notion" not in target_names

    def test_same_text_in_two_todos_is_queued_for_both(
        self, db, user, notebook, notion_todos_integration
    ):
        """De-duplication is per todo, not per content hash."""
        from app.services.sync_queue import queue_todo_sync

        first = queue_todo_sync(db, _todo(db, user, notebook, "Call Bob"), "nb-uuid")
        second = queue_todo_sync(db, _todo(db, user, notebook, "Call Bob"), "nb-uuid")
        assert len(first) == 1 and len(second) == 1
        assert first[0].id != second[0].id

    def test_synced_todo_is_requeued_only_when_it_changed(
        self, db, user, notebook, notion_todos_integration
    ):
        """sync_records decide: same text and state -> nothing; checked -> queued."""
        from app.services.fingerprinting import fingerprint_todo
        from app.services.sync_queue import queue_todo_sync

        todo = _todo(db, user, notebook)
        db.add(
            SyncRecord(
                user_id=user.id,
                target_name="notion-todos",
                item_type="todo",
                item_id=str(todo.id),
                content_hash=fingerprint_todo(todo.text, False, "nb-uuid", 1),
                external_id="page-1",
                status="success",
            )
        )
        db.commit()

        assert queue_todo_sync(db, todo, "nb-uuid") == []
        todo.completed = True
        db.commit()
        entries = queue_todo_sync(db, todo, "nb-uuid")
        assert len(entries) == 1
        # A second change while still pending reuses the row.
        todo.text = "Buy groceries today"
        db.commit()
        again = queue_todo_sync(db, todo, "nb-uuid")
        assert [e.id for e in again] == [entries[0].id]
        assert db.query(SyncQueue).filter_by(item_type="todo").count() == 1


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
