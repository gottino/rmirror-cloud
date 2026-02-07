"""Integration tests for services/sync_worker.py.

Tests the worker's queue processing logic with mocked Notion sync target.
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from app.models.notebook import Notebook
from app.models.page import Page
from app.models.sync_record import IntegrationConfig, SyncQueue, SyncRecord
from app.services.sync_worker import SyncWorker
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
    async def test_failed_sync_increments_retry_count(self, db, user, queue_item, notion_config, page):
        """Failed sync should increment retry_count."""
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
        assert queue_item.status == "failed"
        assert queue_item.error_message == "Notion API error"
        # retry_count incremented once in _process_queue_item (line 155)
        assert queue_item.retry_count == 1

    @pytest.mark.asyncio
    async def test_exception_in_sync_marks_failed(self, db, user, queue_item, notion_config, page):
        """Exception during sync should mark item failed and increment retry."""
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

        # Query fresh to avoid detached instance issues
        result = db.query(SyncQueue).filter(SyncQueue.id == item_id).first()
        assert result.status == "failed"
        assert "Connection refused" in result.error_message
