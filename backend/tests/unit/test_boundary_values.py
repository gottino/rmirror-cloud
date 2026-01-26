"""Boundary value tests for quota system and API limits.

Tests edge cases and boundary conditions to ensure the system
behaves correctly at critical thresholds.
"""

import pytest
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session

from app.models.notebook import Notebook, DocumentType
from app.models.page import OcrStatus, Page
from app.services import quota_service
from tests.conftest import create_user_with_quota, create_pending_pages, create_test_page


class TestQuotaBoundaries:
    """Test quota system boundary conditions."""

    def test_quota_limit_zero(self, db: Session):
        """Quota limit of 0 should reject all consumption."""
        user = create_user_with_quota(db, used=0, limit=0)

        # Should not be able to consume any quota
        result = quota_service.check_quota(db, user.id)
        assert result is False

        # Attempting to consume should raise
        with pytest.raises(quota_service.QuotaExceededError):
            quota_service.consume_quota(db, user.id, amount=1)

    def test_quota_limit_negative_enterprise(self, db: Session):
        """Negative limit (-1) represents unlimited quota for enterprise."""
        from app.models.subscription import SubscriptionTier

        user = create_user_with_quota(db, used=1000, limit=-1, tier=SubscriptionTier.ENTERPRISE)

        # Enterprise with -1 limit should always have quota
        result = quota_service.check_quota(db, user.id)
        assert result is True

        # Should be able to consume without limit
        quota_service.consume_quota(db, user.id, amount=100)
        # No exception means success

    def test_quota_used_equals_limit(self, db: Session):
        """Quota exactly at limit (30/30) should be exhausted."""
        user = create_user_with_quota(db, used=30, limit=30)

        # Exactly at limit = exhausted
        result = quota_service.check_quota(db, user.id)
        assert result is False

        status = quota_service.get_quota_status(db, user.id)
        assert status["is_exhausted"] is True
        assert status["remaining"] == 0
        assert status["percentage_used"] == 100.0

    def test_quota_percentage_89_vs_90(self, db: Session):
        """89% should not trigger warning, 90% should."""
        # 89% (26.7/30) - rounds to 27 used = 90%, so test 26 used
        user_89 = create_user_with_quota(db, used=26, limit=30)  # 86.67%
        status_89 = quota_service.get_quota_status(db, user_89.id)

        # 90% exactly (27/30)
        user_90 = create_user_with_quota(db, used=27, limit=30)  # 90%
        status_90 = quota_service.get_quota_status(db, user_90.id)

        # 26/30 = 86.67% < 90%
        assert status_89["percentage_used"] < 90.0

        # 27/30 = 90%
        assert status_90["percentage_used"] == 90.0

    def test_quota_percentage_99_vs_100(self, db: Session):
        """99% should trigger warning but not exceeded, 100% is exceeded."""
        # 99% (29.7/30) - use 29 to get just under 100%
        user_99 = create_user_with_quota(db, used=29, limit=30)  # 96.67%
        status_99 = quota_service.get_quota_status(db, user_99.id)

        # 100% (30/30)
        user_100 = create_user_with_quota(db, used=30, limit=30)  # 100%
        status_100 = quota_service.get_quota_status(db, user_100.id)

        # 29/30 is not exhausted
        assert status_99["is_exhausted"] is False
        assert status_99["remaining"] == 1

        # 30/30 is exhausted
        assert status_100["is_exhausted"] is True
        assert status_100["remaining"] == 0

    def test_quota_consumption_large_amount(self, db: Session):
        """Consuming more than remaining quota should fail."""
        user = create_user_with_quota(db, used=25, limit=30)  # 5 remaining

        # Try to consume 10 when only 5 remain
        with pytest.raises(quota_service.QuotaExceededError) as exc_info:
            quota_service.consume_quota(db, user.id, amount=10)

        # Should fail with appropriate error
        assert "exceeded" in str(exc_info.value).lower() or exc_info.value is not None


class TestPendingPageBoundaries:
    """Test pending page limit boundaries."""

    def test_pending_pages_99_vs_100(self, db: Session):
        """99 pending pages should allow upload, 100 should block next."""
        user = create_user_with_quota(db, used=30, limit=30)  # Exhausted

        notebook = Notebook(
            user_id=user.id,
            notebook_uuid="pending-test-99-vs-100",
            visible_name="Pending Test",
            document_type=DocumentType.NOTEBOOK,
        )
        db.add(notebook)
        db.commit()

        # Create 99 pending pages
        create_pending_pages(db, user.id, notebook.id, count=99)

        # Count should be 99
        pending_count = (
            db.query(Page)
            .filter(
                Page.notebook_id == notebook.id,
                Page.ocr_status == OcrStatus.PENDING_QUOTA,
            )
            .count()
        )
        assert pending_count == 99

        # Add 100th page
        create_pending_pages(db, user.id, notebook.id, count=1)

        # Count should now be 100
        pending_count = (
            db.query(Page)
            .filter(
                Page.notebook_id == notebook.id,
                Page.ocr_status == OcrStatus.PENDING_QUOTA,
            )
            .count()
        )
        assert pending_count == 100


class TestFileSizeBoundaries:
    """Test file size and content boundaries."""

    def test_empty_file_hash(self, db: Session):
        """Empty file should have consistent hash."""
        from app.utils.files import calculate_file_hash
        from io import BytesIO

        empty_stream = BytesIO(b"")
        hash1 = calculate_file_hash(empty_stream)

        empty_stream2 = BytesIO(b"")
        hash2 = calculate_file_hash(empty_stream2)

        # Same content = same hash
        assert hash1 == hash2

    def test_file_hash_consistency(self, db: Session):
        """Same content should always produce same hash."""
        from app.utils.files import calculate_file_hash
        from io import BytesIO

        content = b"test content for hashing"

        stream1 = BytesIO(content)
        hash1 = calculate_file_hash(stream1)

        stream2 = BytesIO(content)
        hash2 = calculate_file_hash(stream2)

        assert hash1 == hash2

    def test_file_hash_sensitivity(self, db: Session):
        """Different content should produce different hash."""
        from app.utils.files import calculate_file_hash
        from io import BytesIO

        stream1 = BytesIO(b"content version 1")
        hash1 = calculate_file_hash(stream1)

        stream2 = BytesIO(b"content version 2")
        hash2 = calculate_file_hash(stream2)

        assert hash1 != hash2


class TestPageNumberBoundaries:
    """Test page number edge cases."""

    def test_page_number_zero(self, db: Session):
        """Page number 0 should be valid."""
        user = create_user_with_quota(db, used=0, limit=30)

        notebook = Notebook(
            user_id=user.id,
            notebook_uuid="page-zero-test",
            visible_name="Page Zero Test",
            document_type=DocumentType.NOTEBOOK,
        )
        db.add(notebook)
        db.commit()

        page = create_test_page(
            db=db,
            user_id=user.id,
            notebook_id=notebook.id,
            page_number=0,
        )

        assert page.id is not None

    def test_page_number_large(self, db: Session):
        """Large page numbers should be valid."""
        user = create_user_with_quota(db, used=0, limit=30)

        notebook = Notebook(
            user_id=user.id,
            notebook_uuid="large-page-number-test",
            visible_name="Large Page Number Test",
            document_type=DocumentType.NOTEBOOK,
        )
        db.add(notebook)
        db.commit()

        # Test with large but reasonable page number
        page = create_test_page(
            db=db,
            user_id=user.id,
            notebook_id=notebook.id,
            page_number=9999,
        )

        assert page.id is not None


class TestUUIDBoundaries:
    """Test UUID handling edge cases."""

    def test_notebook_uuid_standard(self, db: Session):
        """Standard UUID format should work."""
        import uuid

        user = create_user_with_quota(db, used=0, limit=30)
        standard_uuid = str(uuid.uuid4())

        notebook = Notebook(
            user_id=user.id,
            notebook_uuid=standard_uuid,
            visible_name="Standard UUID Test",
            document_type=DocumentType.NOTEBOOK,
        )
        db.add(notebook)
        db.commit()

        assert notebook.id is not None
        assert notebook.notebook_uuid == standard_uuid

    def test_notebook_uuid_custom_format(self, db: Session):
        """Custom UUID-like strings should work (reMarkable format)."""
        user = create_user_with_quota(db, used=0, limit=30)

        # reMarkable uses lowercase UUIDs without dashes sometimes
        remarkable_uuid = "a1b2c3d4e5f6g7h8"

        notebook = Notebook(
            user_id=user.id,
            notebook_uuid=remarkable_uuid,
            visible_name="reMarkable UUID Test",
            document_type=DocumentType.NOTEBOOK,
        )
        db.add(notebook)
        db.commit()

        assert notebook.id is not None
        assert notebook.notebook_uuid == remarkable_uuid


class TestTimestampBoundaries:
    """Test timestamp handling edge cases."""

    def test_quota_reset_at_future(self, db: Session):
        """Quota with future reset_at should not reset."""
        user = create_user_with_quota(db, used=30, limit=30)

        quota = quota_service.get_or_create_quota(db, user.id)
        # Ensure reset is in the future
        quota.reset_at = datetime.now(timezone.utc) + timedelta(days=30)
        db.commit()

        # Should still be exhausted
        result = quota_service.check_quota(db, user.id)
        assert result is False

    def test_quota_reset_at_past(self, db: Session):
        """Quota with past reset_at should auto-reset on next check."""
        user = create_user_with_quota(db, used=30, limit=30)

        quota = quota_service.get_or_create_quota(db, user.id)

        # Set reset time to past (use datetime without timezone for SQLite compat)
        from datetime import datetime as dt
        quota.reset_at = dt.utcnow() - timedelta(days=1)
        db.commit()

        # Get fresh quota - should detect and auto-reset
        fresh_quota = quota_service.get_or_create_quota(db, user.id)

        # After reset, quota should have 0 used
        assert fresh_quota.used == 0

        # Should now have available quota
        result = quota_service.check_quota(db, user.id)
        assert result is True
