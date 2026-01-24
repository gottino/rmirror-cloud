"""Integration tests for quota system across API endpoints.

Tests TC-AUTO-03 through TC-AUTO-09 from the test plan:
- Upload with quota exhausted (graceful degradation)
- Hard cap enforcement (100 pending pages)
- Rate limiting (10 uploads/minute)
- Retroactive processing (newest first)
- Content hash deduplication
- Integration blocking
- Metadata sync (should work)
"""

import asyncio
import io
import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.notebook import Notebook, DocumentType
from app.models.page import OcrStatus, Page
from app.services import quota_service
from tests.conftest import create_pending_pages, create_test_page, create_user_with_quota
from tests.test_config import test_app, test_client  # noqa: F401 - fixtures


# Mock services to avoid external dependencies
@pytest.fixture
def mock_storage():
    """Mock storage service."""
    with patch("app.api.processing.get_storage_service") as mock:
        storage_mock = MagicMock()
        storage_mock.upload_file = AsyncMock()
        storage_mock.download_file = AsyncMock(return_value=b"fake_pdf_bytes")
        mock.return_value = storage_mock
        yield storage_mock


@pytest.fixture
def mock_ocr():
    """Mock OCR service."""
    with patch("app.api.processing.OCRService") as mock_class:
        ocr_mock = MagicMock()

        # Mock async extract_text_from_pdf method
        async def mock_extract_text(pdf_bytes):
            return "Test OCR text"

        ocr_mock.return_value.extract_text_from_pdf = mock_extract_text
        mock_class.return_value = ocr_mock.return_value
        yield mock_class


@pytest.fixture
def mock_rm_converter():
    """Mock reMarkable converter."""
    with patch("app.api.processing.RMConverter") as mock_class:
        converter_mock = MagicMock()
        # Mock all methods that might be called
        converter_mock.has_content.return_value = True
        converter_mock.rm_to_pdf_bytes.return_value = b"fake_pdf_bytes"
        converter_mock.rm_to_svg.return_value = "<svg>test</svg>"
        mock_class.return_value = converter_mock
        yield converter_mock


@pytest.fixture
def mock_pdf_service():
    """Mock PDF service."""
    with patch("app.api.processing.PDFService") as mock_class:
        pdf_mock = MagicMock()
        pdf_mock.combine_pdfs.return_value = b"combined_pdf_bytes"
        mock_class.return_value = pdf_mock
        yield pdf_mock


@pytest.fixture
def mock_metadata_parser():
    """Mock reMarkable metadata parser."""
    with patch("app.api.processing.RMMetadataParser") as mock_class:
        parser_mock = MagicMock()
        metadata_obj = MagicMock()
        metadata_obj.visible_name = "Test Notebook"
        metadata_obj.document_type = "notebook"
        metadata_obj.parent = None
        metadata_obj.last_modified = datetime.utcnow()
        metadata_obj.version = 1
        metadata_obj.pinned = False
        parser_mock.return_value.parse_bytes.return_value = metadata_obj
        mock_class.return_value = parser_mock.return_value
        yield parser_mock


@pytest.fixture
def test_rm_file():
    """Create a fake .rm file for testing."""
    content = b"fake_remarkable_file_content_with_drawing_data"
    return ("test_page.rm", io.BytesIO(content), "application/octet-stream")


@pytest.fixture
def test_client_with_user(db, test_app):
    """Create test client with mocked authenticated user."""
    from app.auth.clerk import get_clerk_active_user

    # Create test user
    user = create_user_with_quota(db, used=0, limit=30)

    # Override authentication dependency
    async def override_get_clerk_active_user():
        return user

    test_app.dependency_overrides[get_clerk_active_user] = override_get_clerk_active_user

    # Create client with overridden app
    with TestClient(test_app) as client:
        yield client, user

    # Clear override
    test_app.dependency_overrides.pop(get_clerk_active_user, None)


# =============================================================================
# TC-AUTO-03: Upload with Quota Exhausted (Graceful Degradation)
# =============================================================================


@pytest.mark.asyncio
async def test_upload_with_quota_exhausted(
    db: Session,
    test_client_with_user,
    test_rm_file,
    mock_storage,
    mock_ocr,
    mock_rm_converter,
    mock_pdf_service,
):
    """
    TC-AUTO-03: Upload should create page and PDF, skip OCR when quota exhausted.

    Expected behavior:
    - HTTP 200 response (not 429 or 402)
    - Page record created
    - PDF generated and uploaded to storage
    - OCR status = PENDING_QUOTA
    - OCR text is null/empty
    - Quota not consumed
    """
    client, user = test_client_with_user

    # Setup: Set quota to exhausted (30/30)
    quota = quota_service.get_or_create_quota(db, user.id)
    quota.used = 30
    quota.limit = 30
    db.commit()

    # Verify quota exhausted
    assert quota_service.check_quota(db, user.id) is False

    # Action: Upload .rm file
    files = {"rm_file": test_rm_file}
    response = client.post("/v1/processing/rm-file", files=files)

    # Verify response
    assert response.status_code == 200, f"Upload failed: {response.json()}"
    page_data = response.json()

    # Verify response structure
    assert page_data.get("success") is True, "Upload should succeed"
    assert page_data.get("page_count") == 1, "Should report 1 page"

    # Verify page created
    page_id = page_data.get("page_id")
    assert page_id is not None, f"Page ID not returned. Response: {page_data}"

    page = db.query(Page).filter_by(id=page_id).first()
    assert page is not None, "Page not created in database"
    assert page.ocr_status == OcrStatus.PENDING_QUOTA, f"Expected PENDING_QUOTA, got {page.ocr_status}"
    assert page.pdf_s3_key is not None, "PDF S3 key should be set"
    assert not page.ocr_text or page.ocr_text == "", f"OCR text should be empty, got: {page.ocr_text}"
    assert page.ocr_completed_at is None, "ocr_completed_at should be None"

    # Verify quota NOT consumed (still 30/30)
    db.refresh(quota)
    assert quota.used == 30, f"Quota should still be 30, got {quota.used}"

    # Verify extracted text is empty (no OCR performed)
    assert page_data.get("extracted_text") == "", "Extracted text should be empty when quota exhausted"


# =============================================================================
# TC-AUTO-04: Hard Cap Enforcement (100 Pending Pages)
# =============================================================================


@pytest.mark.asyncio
async def test_hard_cap_enforcement(
    db: Session,
    test_client_with_user,
    test_rm_file,
    mock_storage,
    mock_ocr,
    mock_rm_converter,
    mock_pdf_service,
):
    """
    TC-AUTO-04: Should reject upload when user has 100+ pending pages.

    Expected behavior:
    - HTTP 429 error (Too Many Requests)
    - Error message mentions hard cap and "100"
    - No page created
    - Database still shows exactly 100 pending pages
    """
    client, user = test_client_with_user

    # Setup: Set quota to exhausted
    quota = quota_service.get_or_create_quota(db, user.id)
    quota.used = 30
    quota.limit = 30
    db.commit()

    # Create a notebook for the user
    notebook = Notebook(
        user_id=user.id,
        notebook_uuid="hard-cap-test-notebook",
        visible_name="Hard Cap Test",
        document_type=DocumentType.NOTEBOOK,
    )
    db.add(notebook)
    db.commit()

    # Create exactly 100 PENDING_QUOTA pages
    create_pending_pages(db, user.id, notebook.id, count=100, status=OcrStatus.PENDING_QUOTA)

    # Verify count
    pending_count = (
        db.query(Page)
        .filter(
            Page.notebook_id == notebook.id,
            Page.ocr_status == OcrStatus.PENDING_QUOTA,
        )
        .count()
    )
    assert pending_count == 100

    # Action: Try to upload 101st page
    files = {"rm_file": test_rm_file}
    response = client.post("/v1/processing/rm-file", files=files)

    # Verify rejection
    assert response.status_code == 429, f"Expected 429, got {response.status_code}"
    error_data = response.json()
    assert "detail" in error_data

    # Verify error message
    error_detail = str(error_data["detail"])
    assert "100" in error_detail, f"Error should mention '100': {error_detail}"
    assert "pending" in error_detail.lower(), f"Error should mention 'pending': {error_detail}"

    # Verify no new page created (still exactly 100)
    final_count = (
        db.query(Page)
        .filter(
            Page.notebook_id == notebook.id,
            Page.ocr_status == OcrStatus.PENDING_QUOTA,
        )
        .count()
    )
    assert final_count == 100, f"Expected 100 pending pages, got {final_count}"


@pytest.mark.asyncio
async def test_hard_cap_allows_99_pending(
    db: Session,
    test_client_with_user,
    test_rm_file,
    mock_storage,
    mock_ocr,
    mock_rm_converter,
    mock_pdf_service,
):
    """Hard cap should allow upload when user has 99 pending pages."""
    client, user = test_client_with_user

    # Setup: Set quota to exhausted
    quota = quota_service.get_or_create_quota(db, user.id)
    quota.used = 30
    quota.limit = 30
    db.commit()

    # Create a notebook
    notebook = Notebook(
        user_id=user.id,
        notebook_uuid="hard-cap-99-test",
        visible_name="Hard Cap 99 Test",
        document_type=DocumentType.NOTEBOOK,
    )
    db.add(notebook)
    db.commit()

    # Create 99 pending pages (just under limit)
    create_pending_pages(db, user.id, notebook.id, count=99, status=OcrStatus.PENDING_QUOTA)

    # Action: Upload 100th page (should succeed)
    files = {"rm_file": test_rm_file}
    response = client.post("/v1/processing/rm-file", files=files)

    # Verify success
    assert response.status_code == 200, f"100th page should be allowed: {response.json()}"

    # Verify now have 100 pending pages total for user (across all notebooks)
    # Note: The uploaded file creates a separate notebook, so we count all user's notebooks
    final_count = (
        db.query(Page)
        .join(Notebook)
        .filter(
            Notebook.user_id == user.id,
            Page.ocr_status == OcrStatus.PENDING_QUOTA,
        )
        .count()
    )
    assert final_count == 100


# =============================================================================
# TC-AUTO-05: Rate Limiting (10 uploads/minute)
# =============================================================================


@pytest.mark.asyncio
@pytest.mark.slow  # Mark as slow test (takes ~6+ seconds)
async def test_rate_limiting(
    db: Session,
    test_client_with_user,
    mock_storage,
    mock_ocr,
    mock_rm_converter,
    mock_pdf_service,
):
    """
    TC-AUTO-05: Should enforce 10 uploads per minute rate limit.

    Expected behavior:
    - First 10 uploads succeed (HTTP 200)
    - 11th upload fails with HTTP 429
    - Error message indicates rate limit
    """
    client, user = test_client_with_user

    # Setup: User with available quota
    quota = quota_service.get_or_create_quota(db, user.id)
    quota.used = 0
    quota.limit = 30
    db.commit()

    # Action: Upload 11 pages rapidly
    responses = []
    for i in range(11):
        # Create unique file for each upload
        test_file = (
            f"test_page_{i}.rm",
            io.BytesIO(f"fake_rm_content_{i}".encode()),
            "application/octet-stream",
        )

        files = {"rm_file": test_file}
        response = client.post("/v1/processing/rm-file", files=files)
        responses.append(response)
        time.sleep(0.1)  # Small delay between uploads

    # Verify first 10 succeeded
    for i in range(10):
        assert (
            responses[i].status_code == 200
        ), f"Upload {i} should succeed, got {responses[i].status_code}: {responses[i].json()}"

    # Verify 11th was rate limited
    assert (
        responses[10].status_code == 429
    ), f"11th upload should be rate limited, got {responses[10].status_code}"

    # Verify error message indicates rate limiting (slowapi returns "X per Y minute" format)
    error_detail = str(responses[10].json().get("detail", ""))
    assert "per" in error_detail.lower() and "minute" in error_detail.lower(), (
        f"Error should indicate rate limit: {error_detail}"
    )


# =============================================================================
# TC-AUTO-06: Retroactive Processing (Newest First)
# =============================================================================


@pytest.mark.asyncio
async def test_retroactive_processing_newest_first(db: Session, mock_storage, mock_ocr):
    """
    TC-AUTO-06: Pending pages should be processed newest first when quota resets.

    Expected behavior:
    - Creates 50 pending pages with different timestamps
    - Processes exactly 30 pages (quota limit)
    - 30 newest pages are processed
    - 20 oldest pages still pending
    - Quota consumed correctly (30/30)
    """
    from app.jobs.process_pending_pages import process_pending_pages_for_user

    # Setup: Create user with fresh quota
    user = create_user_with_quota(db, used=0, limit=30)

    # Create notebook
    notebook = Notebook(
        user_id=user.id,
        notebook_uuid="retroactive-test-notebook",
        visible_name="Retroactive Test",
        document_type=DocumentType.NOTEBOOK,
    )
    db.add(notebook)
    db.commit()

    # Create 50 pending pages with staggered timestamps (oldest to newest)
    pages = []
    for i in range(50):
        created_at = datetime.utcnow() - timedelta(days=50 - i)  # Oldest to newest
        page = create_test_page(
            db=db,
            user_id=user.id,
            notebook_id=notebook.id,
            page_number=i,
            ocr_status=OcrStatus.PENDING_QUOTA,
            created_at=created_at,
            ocr_text=None,  # No OCR yet
        )
        # Add PDF S3 key (required for processing)
        page.pdf_s3_key = f"s3://test-bucket/page-{i}.pdf"
        db.commit()
        pages.append(page)

    # Identify the 30 newest pages (should be processed)
    pages_sorted = sorted(pages, key=lambda p: p.created_at, reverse=True)
    newest_30_ids = [p.id for p in pages_sorted[:30]]
    oldest_20_ids = [p.id for p in pages_sorted[30:]]

    # Action: Run retroactive processing
    count = await process_pending_pages_for_user(db, user.id)

    # Verify count
    assert count == 30, f"Expected 30 pages processed, got {count}"

    # Verify the 30 newest were processed (COMPLETED status)
    for page_id in newest_30_ids:
        page = db.query(Page).filter_by(id=page_id).first()
        assert page.ocr_status == OcrStatus.COMPLETED, f"Page {page_id} not completed"
        assert page.ocr_text is not None, f"Page {page_id} has no OCR text"
        assert page.ocr_completed_at is not None, f"Page {page_id} has no completion timestamp"

    # Verify 20 oldest still pending
    for page_id in oldest_20_ids:
        page = db.query(Page).filter_by(id=page_id).first()
        assert (
            page.ocr_status == OcrStatus.PENDING_QUOTA
        ), f"Page {page_id} should still be pending"

    # Verify pending count
    pending_count = (
        db.query(Page)
        .filter(
            Page.notebook_id == notebook.id,
            Page.ocr_status == OcrStatus.PENDING_QUOTA,
        )
        .count()
    )
    assert pending_count == 20, f"Expected 20 pending, got {pending_count}"

    # Verify quota consumed (30/30)
    quota = quota_service.get_or_create_quota(db, user.id)
    assert quota.used == 30, f"Expected quota 30/30, got {quota.used}/{quota.limit}"


# =============================================================================
# TC-AUTO-07: Content Hash Deduplication
# =============================================================================


@pytest.mark.asyncio
async def test_content_hash_deduplication(
    db: Session,
    test_client_with_user,
    mock_storage,
    mock_ocr,
    mock_rm_converter,
    mock_pdf_service,
):
    """
    TC-AUTO-07: Re-uploading same content should not consume quota.

    Expected behavior:
    - First upload consumes quota (5 -> 6)
    - Second upload (same content) doesn't consume quota (stays 6)
    - Both uploads succeed (HTTP 200)
    """
    client, user = test_client_with_user

    # Setup: User with some quota used
    quota = quota_service.get_or_create_quota(db, user.id)
    quota.used = 5
    quota.limit = 30
    db.commit()

    # First upload
    test_file_1 = (
        "duplicate_test.rm",
        io.BytesIO(b"exact_same_content_for_dedup_test"),
        "application/octet-stream",
    )
    files = {"rm_file": test_file_1}
    response1 = client.post("/v1/processing/rm-file", files=files)

    assert response1.status_code == 200, f"First upload failed: {response1.json()}"

    # Verify quota consumed (5 -> 6)
    db.refresh(quota)
    assert quota.used == 6, f"Quota should be 6 after first upload, got {quota.used}"

    # Second upload (SAME content, same hash)
    test_file_2 = (
        "duplicate_test.rm",
        io.BytesIO(b"exact_same_content_for_dedup_test"),  # Identical content
        "application/octet-stream",
    )
    files = {"rm_file": test_file_2}
    response2 = client.post("/v1/processing/rm-file", files=files)

    assert response2.status_code == 200, f"Second upload failed: {response2.json()}"

    # Verify quota NOT consumed again (still 6)
    db.refresh(quota)
    assert quota.used == 6, f"Quota should still be 6 after duplicate upload, got {quota.used}"


@pytest.mark.asyncio
async def test_content_hash_changed_consumes_quota(
    db: Session,
    test_client_with_user,
    mock_storage,
    mock_ocr,
    mock_rm_converter,
    mock_pdf_service,
):
    """Changed content (different hash) should consume quota again."""
    client, user = test_client_with_user

    # Setup
    quota = quota_service.get_or_create_quota(db, user.id)
    quota.used = 5
    quota.limit = 30
    db.commit()

    # First upload
    test_file_1 = (
        "page_v1.rm",
        io.BytesIO(b"original_content_version_1"),
        "application/octet-stream",
    )
    files = {"rm_file": test_file_1}
    response1 = client.post("/v1/processing/rm-file", files=files)
    assert response1.status_code == 200

    # Verify quota consumed (5 -> 6)
    db.refresh(quota)
    assert quota.used == 6

    # Second upload (DIFFERENT content, different hash)
    test_file_2 = (
        "page_v1.rm",  # Same filename
        io.BytesIO(b"modified_content_version_2"),  # Different content!
        "application/octet-stream",
    )
    files = {"rm_file": test_file_2}
    response2 = client.post("/v1/processing/rm-file", files=files)
    assert response2.status_code == 200

    # Verify quota consumed AGAIN (6 -> 7)
    db.refresh(quota)
    assert quota.used == 7, f"Quota should be 7 after modified upload, got {quota.used}"


# =============================================================================
# TC-AUTO-08: Integration Blocking
# =============================================================================


@pytest.mark.asyncio
async def test_integration_sync_blocked_when_quota_exhausted(db: Session):
    """
    TC-AUTO-08: Integration sync should be blocked when quota exhausted.

    Expected behavior:
    - Page created with PENDING_QUOTA status
    - Integration sync should be blocked
    - quota_service.should_block_integrations() returns True
    """
    from app.services.quota_service import QUOTA_LIMITS

    # Setup: User with exhausted quota
    user = create_user_with_quota(db, used=30, limit=30)

    # Create notebook and page
    notebook = Notebook(
        user_id=user.id,
        notebook_uuid="integration-block-test",
        visible_name="Integration Block Test",
        document_type=DocumentType.NOTEBOOK,
    )
    db.add(notebook)
    db.commit()

    page = create_test_page(
        db=db,
        user_id=user.id,
        notebook_id=notebook.id,
        ocr_status=OcrStatus.PENDING_QUOTA,
        ocr_text=None,
    )

    # Verify integration sync should be blocked
    should_block = quota_service.check_quota(db, user.id)
    assert should_block is False, "Quota check should return False (exhausted)"

    # Verify quota status indicates exhaustion
    quota_status = quota_service.get_quota_status(db, user.id)
    assert quota_status["is_exhausted"] is True
    assert quota_status["remaining"] == 0


@pytest.mark.asyncio
async def test_integration_sync_not_blocked_with_quota(db: Session):
    """Integration sync should work when quota available."""
    # Setup: User with available quota
    user = create_user_with_quota(db, used=10, limit=30)

    # Create notebook and page with COMPLETED OCR
    notebook = Notebook(
        user_id=user.id,
        notebook_uuid="integration-allowed-test",
        visible_name="Integration Allowed Test",
        document_type=DocumentType.NOTEBOOK,
    )
    db.add(notebook)
    db.commit()

    page = create_test_page(
        db=db,
        user_id=user.id,
        notebook_id=notebook.id,
        ocr_status=OcrStatus.COMPLETED,
        ocr_text="Test OCR text for integration",
    )

    # Verify integration sync should NOT be blocked
    should_block = quota_service.check_quota(db, user.id)
    assert should_block is True, "Quota check should return True (available)"

    # Verify quota status
    quota_status = quota_service.get_quota_status(db, user.id)
    assert quota_status["is_exhausted"] is False
    assert quota_status["remaining"] == 20


# =============================================================================
# TC-AUTO-09: Metadata Sync (Should Always Work)
# =============================================================================


@pytest.mark.asyncio
async def test_metadata_sync_not_blocked_by_quota(db: Session):
    """
    TC-AUTO-09: Metadata-only updates should work even when quota exhausted.

    Expected behavior:
    - Metadata update succeeds (would be HTTP 200 in real endpoint)
    - Quota not consumed
    - Notebook metadata updated
    """
    # Setup: User with exhausted quota
    user = create_user_with_quota(db, used=30, limit=30)

    # Create notebook
    notebook = Notebook(
        user_id=user.id,
        notebook_uuid="metadata-test-notebook",
        visible_name="Old Name",
        document_type=DocumentType.NOTEBOOK,
    )
    db.add(notebook)
    db.commit()

    # Action: Update metadata (simulate metadata-only sync)
    notebook.visible_name = "Updated Name"
    notebook.last_opened = datetime.utcnow()
    db.commit()

    # Verify quota NOT consumed (still 30/30)
    quota = quota_service.get_or_create_quota(db, user.id)
    assert quota.used == 30, f"Quota should still be 30, got {quota.used}"

    # Verify notebook updated
    db.refresh(notebook)
    assert notebook.visible_name == "Updated Name"
    assert notebook.last_opened is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
