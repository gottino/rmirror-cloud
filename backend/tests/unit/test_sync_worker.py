"""Integration tests for services/sync_worker.py.

Tests the worker's queue processing logic with mocked Notion sync target.
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from app.core.sync_engine import SyncResult
from app.models.notebook import Notebook
from app.models.page import Page
from app.models.sync_record import IntegrationConfig, SyncQueue, SyncRecord, SyncStatus
from app.services.sync_worker import (
    MAX_SYNC_RETRIES,
    PROCESSING_LEASE,
    RETRY_BASE_DELAY_SECONDS,
    RETRY_MAX_DELAY_SECONDS,
    SyncWorker,
    apply_sync_failure,
    apply_sync_result,
    compute_retry_delay,
    reclaim_stale_processing,
)
from tests.conftest import create_user_with_quota


@pytest.fixture
def user(db: Session):
    """Create a test user."""
    return create_user_with_quota(db, used=0, limit=30)


@pytest.fixture
def notebook(db: Session, user):
    """Create a test notebook."""
    nb = Notebook(
        notebook_uuid="nb-worker-test",
        user_id=user.id,
        visible_name="Worker Test Notebook",
        document_type="notebook",
        created_at=datetime.utcnow(),
    )
    db.add(nb)
    db.commit()
    db.refresh(nb)
    return nb


@pytest.fixture
def page(db: Session, notebook):
    """Create a test page with OCR text."""
    p = Page(
        notebook_id=notebook.id,
        page_uuid="page-worker-test",
        pdf_s3_key="s3://test/page.pdf",
        file_hash="filehash1",
        ocr_status="completed",
        ocr_text="Test page content for sync",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


@pytest.fixture
def notion_config(db: Session, user):
    """Create an enabled Notion integration config (unencrypted for test)."""
    config = IntegrationConfig(
        user_id=user.id,
        target_name="notion",
        is_enabled=True,
        config_encrypted='{"access_token": "test-token", "database_id": "db-123"}',
    )
    db.add(config)
    db.commit()
    db.refresh(config)
    return config


@pytest.fixture
def queue_item(db: Session, user, page):
    """Create a pending queue item."""
    item = SyncQueue(
        user_id=user.id,
        item_type="page_text",
        item_id=str(page.id),
        content_hash="content_hash_1",
        page_uuid="page-worker-test",
        notebook_uuid="nb-worker-test",
        page_number=1,
        target_name="notion",
        status="pending",
        priority=3,
        scheduled_at=datetime.utcnow() - timedelta(minutes=1),
        created_at=datetime.utcnow() - timedelta(minutes=1),
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


class TestSyncWorkerProcessing:
    """Tests for SyncWorker queue processing."""

    @pytest.mark.asyncio
    async def test_process_pending_completes_item(self, db, user, queue_item, notion_config, page):
        """_process_pending_items should process and complete a pending item."""
        worker = SyncWorker()
        item_id = queue_item.id

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.target_id = "notion-block-123"
        mock_result.metadata = {}

        # Prevent db.close() from detaching our objects
        with patch("app.services.sync_worker.SessionLocal", return_value=db), \
             patch.object(db, "close"), \
             patch("app.services.sync_worker.NotionSyncTarget") as MockTarget:
            mock_target = MagicMock()
            mock_target.sync_item = AsyncMock(return_value=mock_result)
            MockTarget.return_value = mock_target

            with patch.object(IntegrationConfig, "get_config",
                            return_value={"access_token": "test", "database_id": "db-123"}):
                await worker._process_pending_items()

        # Verify via fresh query (queue_item may be detached)
        result = db.query(SyncQueue).filter(SyncQueue.id == item_id).first()
        assert result.status == "completed"

    @pytest.mark.asyncio
    async def test_process_pending_no_items_no_error(self, db):
        """_process_pending_items with empty queue should do nothing."""
        worker = SyncWorker()

        with patch("app.services.sync_worker.SessionLocal", return_value=db), \
             patch.object(db, "close"):
            # Should not raise
            await worker._process_pending_items()

    @pytest.mark.asyncio
    async def test_process_queue_item_creates_sync_record(self, db, user, queue_item, notion_config, page):
        """Successful sync should create a SyncRecord."""
        worker = SyncWorker()

        queue_item.status = "processing"
        db.commit()

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.target_id = "notion-block-456"
        mock_result.metadata = {}

        with patch("app.services.sync_worker.NotionSyncTarget") as MockTarget:
            mock_target = MagicMock()
            mock_target.sync_item = AsyncMock(return_value=mock_result)
            MockTarget.return_value = mock_target

            with patch.object(IntegrationConfig, "get_config",
                            return_value={"access_token": "test", "database_id": "db-123"}):
                await worker._process_queue_item(db, queue_item)

        # Verify SyncRecord created
        record = (
            db.query(SyncRecord)
            .filter(
                SyncRecord.user_id == user.id,
                SyncRecord.page_uuid == "page-worker-test",
            )
            .first()
        )
        assert record is not None
        assert record.external_id == "notion-block-456"
        assert record.status == "success"

    @pytest.mark.asyncio
    async def test_process_queue_item_fails_without_config(self, db, user, queue_item):
        """Missing integration config should mark item as failed."""
        worker = SyncWorker()

        queue_item.status = "processing"
        db.commit()

        await worker._process_queue_item(db, queue_item)

        db.refresh(queue_item)
        assert queue_item.status == "failed"
        assert "not active" in queue_item.error_message

    @pytest.mark.asyncio
    async def test_process_page_sync_skips_unchanged(self, db, user, queue_item, notion_config, page):
        """Page sync should skip if content_hash unchanged."""
        worker = SyncWorker()

        queue_item.status = "processing"
        db.commit()

        # Create existing sync record with same hash
        existing_record = SyncRecord(
            user_id=user.id,
            target_name="notion",
            item_type="page_text",
            item_id=str(page.id),
            content_hash="content_hash_1",  # Same as queue_item
            external_id="existing-block",
            status="success",
            page_uuid="page-worker-test",
            notebook_uuid="nb-worker-test",
            synced_at=datetime.utcnow(),
        )
        db.add(existing_record)
        db.commit()

        with patch.object(IntegrationConfig, "get_config",
                        return_value={"access_token": "test", "database_id": "db-123"}):
            await worker._process_queue_item(db, queue_item)

        db.refresh(queue_item)
        assert queue_item.status == "completed"

    @pytest.mark.asyncio
    async def test_process_page_sync_updates_existing_record(self, db, user, queue_item, notion_config, page):
        """Re-sync with changed content should update existing SyncRecord."""
        worker = SyncWorker()

        queue_item.status = "processing"
        queue_item.content_hash = "new_hash"
        db.commit()

        # Create existing record with old hash
        existing_record = SyncRecord(
            user_id=user.id,
            target_name="notion",
            item_type="page_text",
            item_id=str(page.id),
            content_hash="old_hash",
            external_id="existing-block",
            status="success",
            page_uuid="page-worker-test",
            notebook_uuid="nb-worker-test",
            synced_at=datetime.utcnow(),
        )
        db.add(existing_record)
        db.commit()

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.target_id = "updated-block"
        mock_result.metadata = {}

        with patch("app.services.sync_worker.NotionSyncTarget") as MockTarget:
            mock_target = MagicMock()
            mock_target.sync_item = AsyncMock(return_value=mock_result)
            MockTarget.return_value = mock_target

            with patch.object(IntegrationConfig, "get_config",
                            return_value={"access_token": "test", "database_id": "db-123"}):
                await worker._process_queue_item(db, queue_item)

        db.refresh(existing_record)
        assert existing_record.content_hash == "new_hash"
        assert existing_record.external_id == "updated-block"

    @pytest.mark.asyncio
    async def test_result_failure_reschedules_with_backoff(self, db, user, queue_item, notion_config, page):
        """A transient result failure (success=False) reschedules for retry, not 'failed'."""
        worker = SyncWorker()

        queue_item.status = "processing"
        queue_item.retry_count = 0
        db.commit()

        mock_result = MagicMock()
        mock_result.success = False
        mock_result.error_message = "Notion API error"
        mock_result.metadata = {}

        with patch("app.services.sync_worker.NotionSyncTarget") as MockTarget:
            mock_target = MagicMock()
            mock_target.sync_item = AsyncMock(return_value=mock_result)
            MockTarget.return_value = mock_target

            with patch.object(IntegrationConfig, "get_config",
                            return_value={"access_token": "test", "database_id": "db-123"}):
                await worker._process_queue_item(db, queue_item)

        db.refresh(queue_item)
        # Transient failure -> back to pending with a future scheduled_at, retry_count == 1
        assert queue_item.status == "pending"
        assert queue_item.retry_count == 1
        assert queue_item.error_message == "Notion API error"
        assert queue_item.scheduled_at > datetime.utcnow()

    @pytest.mark.asyncio
    async def test_exception_in_sync_reschedules_for_retry(self, db, user, queue_item, notion_config, page):
        """An exception during sync reschedules for retry (not immediate 'failed')."""
        worker = SyncWorker()
        item_id = queue_item.id

        with patch("app.services.sync_worker.NotionSyncTarget") as MockTarget, \
             patch("app.services.sync_worker.SessionLocal", return_value=db), \
             patch.object(db, "close"):
            mock_target = MagicMock()
            mock_target.sync_item = AsyncMock(side_effect=Exception("Connection refused"))
            MockTarget.return_value = mock_target

            with patch.object(IntegrationConfig, "get_config",
                            return_value={"access_token": "test", "database_id": "db-123"}):
                await worker._process_pending_items()

        result = db.query(SyncQueue).filter(SyncQueue.id == item_id).first()
        assert result.status == "pending"
        assert result.retry_count == 1
        assert "Connection refused" in result.error_message
        assert result.scheduled_at > datetime.utcnow()

    @pytest.mark.asyncio
    async def test_successful_sync_does_not_increment_retry_count(self, db, user, queue_item, notion_config, page):
        """A successful sync leaves retry_count at 0 (no per-attempt over-increment)."""
        worker = SyncWorker()
        item_id = queue_item.id

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.target_id = "notion-block-1"
        mock_result.metadata = {}

        with patch("app.services.sync_worker.SessionLocal", return_value=db), \
             patch.object(db, "close"), \
             patch("app.services.sync_worker.NotionSyncTarget") as MockTarget:
            mock_target = MagicMock()
            mock_target.sync_item = AsyncMock(return_value=mock_result)
            MockTarget.return_value = mock_target

            with patch.object(IntegrationConfig, "get_config",
                            return_value={"access_token": "test", "database_id": "db-123"}):
                await worker._process_pending_items()

        result = db.query(SyncQueue).filter(SyncQueue.id == item_id).first()
        assert result.status == "completed"
        assert result.retry_count == 0

    @pytest.mark.asyncio
    async def test_retries_exhausted_dead_letters(self, db, user, queue_item, notion_config, page):
        """Once retry_count reaches MAX_SYNC_RETRIES the item is dead-lettered ('failed')."""
        worker = SyncWorker()
        item_id = queue_item.id
        queue_item.retry_count = MAX_SYNC_RETRIES - 1  # one failure away from the cap
        db.commit()

        with patch("app.services.sync_worker.SessionLocal", return_value=db), \
             patch.object(db, "close"), \
             patch("app.services.sync_worker.NotionSyncTarget") as MockTarget:
            mock_target = MagicMock()
            mock_target.sync_item = AsyncMock(side_effect=Exception("still failing"))
            MockTarget.return_value = mock_target

            with patch.object(IntegrationConfig, "get_config",
                            return_value={"access_token": "test", "database_id": "db-123"}):
                await worker._process_pending_items()

        result = db.query(SyncQueue).filter(SyncQueue.id == item_id).first()
        assert result.status == "failed"
        assert result.retry_count == MAX_SYNC_RETRIES

    @pytest.mark.asyncio
    async def test_permanent_failure_is_not_retried(self, db, user, queue_item, page):
        """A permanent failure (no integration config) fails immediately, no retry scheduled."""
        worker = SyncWorker()
        # Note: no notion_config fixture -> integration is missing -> permanent failure
        await worker._process_queue_item(db, queue_item)

        db.refresh(queue_item)
        assert queue_item.status == "failed"
        assert queue_item.retry_count == 0  # not a transient error; no retry consumed


class TestRetryPolicy:
    """Unit tests for the retry/backoff helpers."""

    def test_compute_retry_delay_is_exponential(self):
        assert compute_retry_delay(1) == timedelta(seconds=RETRY_BASE_DELAY_SECONDS)
        assert compute_retry_delay(2) == timedelta(seconds=RETRY_BASE_DELAY_SECONDS * 2)
        assert compute_retry_delay(3) == timedelta(seconds=RETRY_BASE_DELAY_SECONDS * 4)

    def test_compute_retry_delay_is_capped(self):
        assert compute_retry_delay(99) == timedelta(seconds=RETRY_MAX_DELAY_SECONDS)

    def test_apply_failure_reschedules_within_max(self):
        now = datetime(2026, 6, 7, 12, 0, 0)
        item = SyncQueue(status="processing", retry_count=0)
        retried = apply_sync_failure(item, "boom", now=now)

        assert retried is True
        assert item.retry_count == 1
        assert item.status == "pending"
        assert item.error_message == "boom"
        assert item.scheduled_at == now + timedelta(seconds=RETRY_BASE_DELAY_SECONDS)

    def test_apply_failure_dead_letters_at_max(self):
        now = datetime(2026, 6, 7, 12, 0, 0)
        item = SyncQueue(status="processing", retry_count=MAX_SYNC_RETRIES - 1)
        retried = apply_sync_failure(item, "boom", now=now)

        assert retried is False
        assert item.retry_count == MAX_SYNC_RETRIES
        assert item.status == "failed"


class TestSyncResultStatus:
    """The worker follows the status the sync target reports."""

    NOW = datetime(2026, 6, 7, 12, 0, 0)

    def _item(self, retry_count=0):
        return SyncQueue(status="processing", retry_count=retry_count)

    def test_skipped_completes_without_retry(self):
        item = self._item()
        outcome = apply_sync_result(item, SyncResult(status=SyncStatus.SKIPPED), now=self.NOW)

        assert outcome == "skipped"
        assert item.status == "completed"
        assert item.completed_at == self.NOW
        assert item.retry_count == 0

    def test_retry_status_reschedules(self):
        item = self._item()
        result = SyncResult(status=SyncStatus.RETRY, error_message="Rate limited by Todoist")
        outcome = apply_sync_result(item, result, now=self.NOW)

        assert outcome == "retry"
        assert item.status == "pending"
        assert item.retry_count == 1
        assert item.scheduled_at == self.NOW + timedelta(seconds=RETRY_BASE_DELAY_SECONDS)

    def test_retry_after_is_honoured(self):
        item = self._item()
        later = self.NOW + timedelta(minutes=30)
        result = SyncResult(status=SyncStatus.RETRY, error_message="rate limited", retry_after=later)
        apply_sync_result(item, result, now=self.NOW)

        assert item.scheduled_at == later

    @pytest.mark.parametrize(
        "message",
        [
            "Can't edit block that is archived. You must unarchive the block before editing.",
            "Client error '401 Unauthorized' for url 'https://api.todoist.com/api/v1/tasks'",
            "Could not find block with ID: abc",
        ],
    )
    def test_permanent_failure_is_not_retried(self, message):
        item = self._item()
        result = SyncResult(status=SyncStatus.FAILED, error_message=message)
        outcome = apply_sync_result(item, result, now=self.NOW)

        assert outcome == "failed"
        assert item.status == "failed"
        assert item.retry_count == 0
        assert item.error_message == message

    @pytest.mark.parametrize(
        "message",
        ["Server error '503 Service Unavailable'", "Connection refused", "Read timed out"],
    )
    def test_transient_failure_is_retried(self, message):
        item = self._item()
        result = SyncResult(status=SyncStatus.FAILED, error_message=message)
        outcome = apply_sync_result(item, result, now=self.NOW)

        assert outcome == "retry"
        assert item.status == "pending"
        assert item.retry_count == 1

    def test_transient_failure_dead_letters_at_cap(self):
        item = self._item(retry_count=MAX_SYNC_RETRIES - 1)
        result = SyncResult(status=SyncStatus.RETRY, error_message="rate limited")
        outcome = apply_sync_result(item, result, now=self.NOW)

        assert outcome == "failed"
        assert item.status == "failed"

    def test_backoff_reaches_the_cap_before_dead_lettering(self):
        """The 1h cap is reachable within MAX_SYNC_RETRIES, so outages up to ~2h survive."""
        assert compute_retry_delay(MAX_SYNC_RETRIES - 1) == timedelta(seconds=RETRY_MAX_DELAY_SECONDS)


class TestFailureRecovery:
    @pytest.mark.asyncio
    async def test_db_error_during_sync_is_rolled_back_and_rescheduled(
        self, db, user, queue_item, notion_config, page
    ):
        """A DB error mid-sync must not leave the item stuck in 'processing'."""
        from sqlalchemy.exc import IntegrityError

        worker = SyncWorker()
        item_id = queue_item.id

        async def failing_process(session, item):
            item.error_message = "partial write that must be discarded"
            raise IntegrityError("INSERT INTO sync_records", {}, Exception("UNIQUE constraint failed"))

        with patch("app.services.sync_worker.SessionLocal", return_value=db), \
             patch.object(db, "close"), \
             patch.object(SyncWorker, "_process_queue_item", side_effect=failing_process):
            await worker._process_pending_items()

        result = db.query(SyncQueue).filter(SyncQueue.id == item_id).first()
        assert result.status == "pending"
        assert result.retry_count == 1
        assert "UNIQUE constraint failed" in result.error_message


def _stuck(item, *, age, retry_count=0):
    item.status = "processing"
    item.started_at = None if age is None else datetime.utcnow() - age
    item.retry_count = retry_count
    return item


class TestStaleProcessingReclaim:
    def test_stale_row_returns_to_pending_immediately_retryable(self, db, queue_item):
        _stuck(queue_item, age=PROCESSING_LEASE + timedelta(minutes=1), retry_count=2)
        db.commit()
        now = datetime.utcnow()

        assert reclaim_stale_processing(db, now=now) == (1, 0)

        db.refresh(queue_item)
        assert queue_item.status == "pending"
        assert queue_item.retry_count == 3
        assert queue_item.scheduled_at == now
        assert queue_item.error_message

    def test_null_started_at_counts_as_stale(self, db, queue_item):
        _stuck(queue_item, age=None)
        db.commit()
        assert reclaim_stale_processing(db) == (1, 0)
        db.refresh(queue_item)
        assert queue_item.status == "pending"

    def test_fresh_row_is_left_alone(self, db, queue_item):
        _stuck(queue_item, age=PROCESSING_LEASE - timedelta(minutes=1))
        db.commit()
        assert reclaim_stale_processing(db) == (0, 0)
        db.refresh(queue_item)
        assert queue_item.status == "processing"
        assert queue_item.retry_count == 0

    def test_dead_letters_when_attempts_exhausted(self, db, queue_item):
        _stuck(queue_item, age=PROCESSING_LEASE * 2, retry_count=MAX_SYNC_RETRIES - 1)
        db.commit()
        assert reclaim_stale_processing(db) == (0, 1)
        db.refresh(queue_item)
        assert queue_item.status == "failed"
        assert queue_item.retry_count == MAX_SYNC_RETRIES
        assert "giving up" in queue_item.error_message

    def test_second_sweep_does_not_double_count(self, db, queue_item):
        """Two workers sweeping in turn: the second finds nothing left to take."""
        _stuck(queue_item, age=PROCESSING_LEASE * 2)
        db.commit()
        assert reclaim_stale_processing(db) == (1, 0)
        assert reclaim_stale_processing(db) == (0, 0)
        db.refresh(queue_item)
        assert queue_item.retry_count == 1

    @pytest.mark.asyncio
    async def test_sweep_retries_stranded_row(self, db, user, queue_item, notion_config, page):
        _stuck(queue_item, age=PROCESSING_LEASE * 2)
        db.commit()
        item_id = queue_item.id

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.target_id = "notion-block-123"
        mock_result.metadata = {}

        with patch("app.services.sync_worker.SessionLocal", return_value=db), \
             patch.object(db, "close"), \
             patch("app.services.sync_worker.NotionSyncTarget") as MockTarget:
            MockTarget.return_value.sync_item = AsyncMock(return_value=mock_result)
            with patch.object(IntegrationConfig, "get_config",
                              return_value={"access_token": "t", "database_id": "d"}):
                await SyncWorker()._process_pending_items()

        result = db.query(SyncQueue).filter(SyncQueue.id == item_id).first()
        assert result.status == "completed"


class TestBatchLeaseAndShutdown:
    def _two_items(self, db, user, queue_item):
        second = SyncQueue(
            user_id=user.id, item_type="page_text", item_id="999",
            content_hash="content_hash_2", page_uuid="page-2", target_name="notion",
            status="pending", priority=3,
            scheduled_at=datetime.utcnow() - timedelta(minutes=1),
            created_at=datetime.utcnow(),
        )
        db.add(second)
        db.commit()
        return queue_item, second

    @pytest.mark.asyncio
    async def test_started_at_refreshed_before_each_item(self, db, user, queue_item):
        first, second = self._two_items(db, user, queue_item)
        seen = {}
        stale = datetime.utcnow() - timedelta(minutes=30)

        async def fake_process(session, item):
            seen[item.id] = item.started_at
            item.status = "completed"
            session.commit()
            # Simulate a long item: age the other row's claim timestamp.
            session.query(SyncQueue).filter(SyncQueue.id != item.id).update(
                {"started_at": stale}, synchronize_session=False
            )
            session.commit()

        with patch("app.services.sync_worker.SessionLocal", return_value=db), \
             patch.object(db, "close"), \
             patch.object(SyncWorker, "_process_queue_item", side_effect=fake_process):
            await SyncWorker()._process_pending_items()

        # The second item's claim stamp was aged during the first item, yet it
        # was renewed right before it ran.
        assert seen[second.id] > datetime.utcnow() - timedelta(minutes=1)

    @pytest.mark.asyncio
    async def test_item_reclaimed_elsewhere_is_not_run(self, db, user, queue_item):
        first, second = self._two_items(db, user, queue_item)
        ran = []

        async def fake_process(session, item):
            ran.append(item.id)
            item.status = "completed"
            # Another sweep reclaims the not-yet-started second item.
            session.query(SyncQueue).filter(SyncQueue.id == second.id).update(
                {"status": "pending"}, synchronize_session=False
            )
            session.commit()

        with patch("app.services.sync_worker.SessionLocal", return_value=db), \
             patch.object(db, "close"), \
             patch.object(SyncWorker, "_process_queue_item", side_effect=fake_process):
            await SyncWorker()._process_pending_items()

        assert ran == [first.id]

    @pytest.mark.asyncio
    async def test_cancellation_releases_unstarted_rows(self, db, user, queue_item):
        import asyncio

        first, second = self._two_items(db, user, queue_item)
        first_id, second_id = first.id, second.id

        async def cancelled(session, item):
            raise asyncio.CancelledError()

        with patch("app.services.sync_worker.SessionLocal", return_value=db), \
             patch.object(db, "close"), \
             patch.object(SyncWorker, "_process_queue_item", side_effect=cancelled):
            with pytest.raises(asyncio.CancelledError):
                await SyncWorker()._process_pending_items()

        by_id = {r.id: r for r in db.query(SyncQueue).all()}
        # Order is by created_at, so `first` ran (in flight) and `second` was unstarted.
        assert by_id[first_id].status == "processing"  # left to the lease reclaim
        assert by_id[second_id].status == "pending"
        assert by_id[second_id].retry_count == 0
