"""Tests for per-notebook deletion feature."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.notebooks import router as notebooks_router
from app.api.sync import router as sync_router
from app.auth.clerk import get_clerk_active_user
from app.database import get_db
from app.dependencies import get_storage_service
from app.models.deleted_notebook import DeletedNotebook
from app.models.notebook import Notebook
from app.models.page import Page
from app.models.sync_record import SyncQueue, SyncRecord
from app.models.user import User


# --- Fixtures ---


def _create_user(db: Session) -> User:
    user = User(
        email="delete-test@example.com",
        full_name="Delete Test User",
        clerk_user_id="clerk_delete_test",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _create_notebook_with_pages(db: Session, user: User, num_pages: int = 3) -> Notebook:
    notebook = Notebook(
        user_id=user.id,
        notebook_uuid="test-nb-uuid-123",
        visible_name="Test Notebook",
        document_type="notebook",
        s3_key="users/1/notebooks/test-nb-uuid-123/original.rm",
        notebook_pdf_s3_key="users/1/notebooks/test-nb-uuid-123/notebook.pdf",
    )
    db.add(notebook)
    db.flush()

    for i in range(num_pages):
        page = Page(
            notebook_id=notebook.id,
            page_uuid=f"page-uuid-{i}",
            s3_key=f"users/1/pages/page-uuid-{i}.rm",
            pdf_s3_key=f"users/1/pages/page-uuid-{i}.pdf",
            ocr_status="completed",
        )
        db.add(page)

    db.commit()
    db.refresh(notebook)
    return notebook


def _create_sync_records(db: Session, user: User, notebook: Notebook) -> int:
    """Create sync records for notebook and return count."""
    count = 0
    # Notebook-level record
    db.add(SyncRecord(
        user_id=user.id,
        notebook_uuid=notebook.notebook_uuid,
        target_name="notion",
        item_type="notebook",
        content_hash="hash-nb",
        external_id="notion-page-id-123",
        status="success",
        synced_at=datetime.utcnow(),
    ))
    count += 1

    # Page-level records
    for page in notebook.pages:
        db.add(SyncRecord(
            user_id=user.id,
            notebook_uuid=notebook.notebook_uuid,
            page_uuid=page.page_uuid,
            target_name="notion",
            item_type="page_text",
            content_hash=f"hash-{page.page_uuid}",
            external_id=f"notion-block-{page.page_uuid}",
            status="success",
            synced_at=datetime.utcnow(),
        ))
        count += 1

    db.commit()
    return count


def _create_sync_queue_entries(db: Session, user: User, notebook: Notebook) -> int:
    """Create pending sync queue entries and return count."""
    count = 0
    for page in notebook.pages:
        db.add(SyncQueue(
            user_id=user.id,
            notebook_uuid=notebook.notebook_uuid,
            page_uuid=page.page_uuid,
            target_name="notion",
            item_type="page_text",
            item_id=page.page_uuid,
            content_hash=f"queue-hash-{page.page_uuid}",
            status="pending",
        ))
        count += 1
    db.commit()
    return count


def _create_app(db: Session, user: User, storage=None):
    app = FastAPI()
    app.include_router(notebooks_router, prefix="/notebooks")
    app.include_router(sync_router, prefix="/sync")

    def _get_db():
        yield db

    async def _get_user():
        return user

    if storage is None:
        storage = MagicMock()
        storage.delete_file = AsyncMock(return_value=True)

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_clerk_active_user] = _get_user
    app.dependency_overrides[get_storage_service] = lambda: storage

    return TestClient(app)


# --- DELETE endpoint tests ---


class TestDeleteNotebook:
    def test_complete_deletion(self, db: Session):
        """Delete removes notebook, pages, sync records, queue entries, and creates tombstone."""
        user = _create_user(db)
        notebook = _create_notebook_with_pages(db, user, num_pages=3)
        nb_id = notebook.id
        sync_count = _create_sync_records(db, user, notebook)
        queue_count = _create_sync_queue_entries(db, user, notebook)

        client = _create_app(db, user)
        response = client.delete(f"/notebooks/{nb_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["notebook_uuid"] == "test-nb-uuid-123"
        assert data["visible_name"] == "Test Notebook"
        assert data["pages_deleted"] == 3
        assert data["sync_records_deleted"] == sync_count
        assert data["notion_cleanup"] == "skipped"

        # Verify notebook and pages are gone
        assert db.query(Notebook).filter(Notebook.id == nb_id).first() is None
        assert db.query(Page).filter(Page.notebook_id == nb_id).count() == 0

        # Verify sync records are gone
        assert db.query(SyncRecord).filter(
            SyncRecord.user_id == user.id,
            SyncRecord.notebook_uuid == "test-nb-uuid-123",
        ).count() == 0

        # Verify sync queue entries are gone
        assert db.query(SyncQueue).filter(
            SyncQueue.user_id == user.id,
            SyncQueue.notebook_uuid == "test-nb-uuid-123",
        ).count() == 0

        # Verify tombstone was created
        tombstone = db.query(DeletedNotebook).filter(
            DeletedNotebook.user_id == user.id,
            DeletedNotebook.notebook_uuid == "test-nb-uuid-123",
        ).first()
        assert tombstone is not None
        assert tombstone.visible_name == "Test Notebook"
        assert tombstone.deleted_at is not None

    def test_s3_cleanup(self, db: Session):
        """Delete calls storage.delete_file for all S3 keys."""
        user = _create_user(db)
        notebook = _create_notebook_with_pages(db, user, num_pages=2)

        storage = MagicMock()
        storage.delete_file = AsyncMock(return_value=True)

        client = _create_app(db, user, storage=storage)
        response = client.delete(f"/notebooks/{notebook.id}")

        assert response.status_code == 200
        data = response.json()
        # 1 notebook s3_key + 1 notebook_pdf_s3_key + 2 page s3_keys + 2 page pdf_s3_keys = 6
        assert data["s3_files_deleted"] == 6
        assert storage.delete_file.call_count == 6

    def test_s3_partial_failure(self, db: Session):
        """S3 failure doesn't block deletion."""
        user = _create_user(db)
        notebook = _create_notebook_with_pages(db, user, num_pages=1)

        storage = MagicMock()
        storage.delete_file = AsyncMock(side_effect=Exception("S3 error"))

        client = _create_app(db, user, storage=storage)
        response = client.delete(f"/notebooks/{notebook.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["s3_files_deleted"] == 0
        assert data["pages_deleted"] == 1
        # Notebook should still be deleted from DB
        assert db.query(Notebook).filter(Notebook.id == notebook.id).first() is None

    def test_tombstone_upsert(self, db: Session):
        """Re-deleting same notebook_uuid updates existing tombstone."""
        user = _create_user(db)

        # Create first tombstone manually
        db.add(DeletedNotebook(
            user_id=user.id,
            notebook_uuid="test-nb-uuid-123",
            visible_name="Old Name",
            deleted_at=datetime(2025, 1, 1),
        ))
        db.commit()

        notebook = _create_notebook_with_pages(db, user, num_pages=1)
        client = _create_app(db, user)
        response = client.delete(f"/notebooks/{notebook.id}")

        assert response.status_code == 200

        # Should still be exactly one tombstone
        tombstones = db.query(DeletedNotebook).filter(
            DeletedNotebook.user_id == user.id,
            DeletedNotebook.notebook_uuid == "test-nb-uuid-123",
        ).all()
        assert len(tombstones) == 1
        assert tombstones[0].visible_name == "Test Notebook"  # Updated
        assert tombstones[0].deleted_at.year == datetime.utcnow().year  # Updated

    def test_not_found(self, db: Session):
        """Delete returns 404 for non-existent notebook."""
        user = _create_user(db)
        client = _create_app(db, user)
        response = client.delete("/notebooks/99999")
        assert response.status_code == 404

    def test_cannot_delete_other_user(self, db: Session):
        """Users cannot delete other users' notebooks."""
        user1 = _create_user(db)
        user2 = User(
            email="other@example.com",
            full_name="Other User",
            clerk_user_id="clerk_other",
        )
        db.add(user2)
        db.commit()

        notebook = _create_notebook_with_pages(db, user2, num_pages=1)

        # Try to delete as user1
        client = _create_app(db, user1)
        response = client.delete(f"/notebooks/{notebook.id}")
        assert response.status_code == 404


# --- Deleted notebooks agent endpoints tests ---


class TestDeletedNotebooksEndpoints:
    def test_get_deleted_notebooks(self, db: Session):
        """GET /sync/deleted-notebooks returns tombstones."""
        user = _create_user(db)
        db.add(DeletedNotebook(
            user_id=user.id,
            notebook_uuid="deleted-uuid-1",
            visible_name="Deleted Notebook",
        ))
        db.commit()

        client = _create_app(db, user)
        response = client.get("/sync/deleted-notebooks")

        assert response.status_code == 200
        data = response.json()
        assert len(data["deleted_notebooks"]) == 1
        assert data["deleted_notebooks"][0]["notebook_uuid"] == "deleted-uuid-1"
        assert data["deleted_notebooks"][0]["visible_name"] == "Deleted Notebook"

    def test_get_empty_deleted_notebooks(self, db: Session):
        """GET /sync/deleted-notebooks returns empty list when none exist."""
        user = _create_user(db)
        client = _create_app(db, user)
        response = client.get("/sync/deleted-notebooks")

        assert response.status_code == 200
        assert response.json()["deleted_notebooks"] == []

    def test_acknowledge_resync(self, db: Session):
        """POST acknowledge with resync deletes tombstone."""
        user = _create_user(db)
        db.add(DeletedNotebook(
            user_id=user.id,
            notebook_uuid="resync-uuid",
            visible_name="Resync Me",
        ))
        db.commit()

        client = _create_app(db, user)
        response = client.post(
            "/sync/deleted-notebooks/resync-uuid/acknowledge",
            json={"action": "resync"},
        )

        assert response.status_code == 200
        assert response.json()["action"] == "resync"

        # Tombstone should be gone
        assert db.query(DeletedNotebook).filter(
            DeletedNotebook.notebook_uuid == "resync-uuid"
        ).first() is None

    def test_acknowledge_dismiss(self, db: Session):
        """POST acknowledge with dismiss deletes tombstone."""
        user = _create_user(db)
        db.add(DeletedNotebook(
            user_id=user.id,
            notebook_uuid="dismiss-uuid",
            visible_name="Dismiss Me",
        ))
        db.commit()

        client = _create_app(db, user)
        response = client.post(
            "/sync/deleted-notebooks/dismiss-uuid/acknowledge",
            json={"action": "dismiss"},
        )

        assert response.status_code == 200
        assert response.json()["action"] == "dismiss"

        assert db.query(DeletedNotebook).filter(
            DeletedNotebook.notebook_uuid == "dismiss-uuid"
        ).first() is None

    def test_acknowledge_not_found(self, db: Session):
        """POST acknowledge returns 404 for missing tombstone."""
        user = _create_user(db)
        client = _create_app(db, user)
        response = client.post(
            "/sync/deleted-notebooks/nonexistent/acknowledge",
            json={"action": "resync"},
        )
        assert response.status_code == 404

    def test_acknowledge_invalid_action(self, db: Session):
        """POST acknowledge rejects invalid action."""
        user = _create_user(db)
        db.add(DeletedNotebook(
            user_id=user.id,
            notebook_uuid="test-uuid",
            visible_name="Test",
        ))
        db.commit()

        client = _create_app(db, user)
        response = client.post(
            "/sync/deleted-notebooks/test-uuid/acknowledge",
            json={"action": "invalid"},
        )
        assert response.status_code == 400
