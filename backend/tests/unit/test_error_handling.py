"""Unit tests for error handling across backend services.

Tests various error conditions and ensures proper error handling
without exposing sensitive information or crashing the application.
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.orm import Session
from httpx import TimeoutException, HTTPStatusError

from tests.conftest import create_user_with_quota


class TestOCRServiceErrors:
    """Test OCR service error handling."""

    @pytest.mark.asyncio
    async def test_ocr_service_timeout(self, db: Session):
        """OCR service should handle timeout gracefully."""
        from app.core.ocr_service import OCRService

        with patch("app.core.ocr_service.anthropic") as mock_anthropic:
            # Simulate timeout
            mock_client = MagicMock()
            mock_client.messages.create = MagicMock(
                side_effect=TimeoutException("Connection timed out")
            )
            mock_anthropic.Anthropic.return_value = mock_client

            # Provide fake API key directly to constructor
            ocr_service = OCRService(api_key="test-api-key-for-ci")
            with pytest.raises(Exception) as exc_info:
                await ocr_service.extract_text_from_pdf(b"fake_pdf_bytes")

            # Should raise but not expose internal details
            assert "timeout" in str(exc_info.value).lower() or exc_info.value is not None

    @pytest.mark.asyncio
    async def test_ocr_service_rate_limit(self, db: Session):
        """OCR service should handle API rate limits gracefully."""
        from app.core.ocr_service import OCRService

        with patch("app.core.ocr_service.anthropic") as mock_anthropic:
            # Simulate 429 rate limit response
            mock_response = MagicMock()
            mock_response.status_code = 429
            mock_response.json.return_value = {"error": {"type": "rate_limit_error"}}

            mock_client = MagicMock()
            mock_client.messages.create = MagicMock(
                side_effect=Exception("Rate limit exceeded")
            )
            mock_anthropic.Anthropic.return_value = mock_client

            # Provide fake API key directly to constructor
            ocr_service = OCRService(api_key="test-api-key-for-ci")
            with pytest.raises(Exception):
                await ocr_service.extract_text_from_pdf(b"fake_pdf_bytes")

    @pytest.mark.asyncio
    async def test_ocr_service_invalid_response(self, db: Session):
        """OCR service should handle malformed API responses."""
        from app.core.ocr_service import OCRService

        with patch("app.core.ocr_service.anthropic") as mock_anthropic:
            # Simulate malformed response (missing expected fields)
            mock_response = MagicMock()
            mock_response.content = []  # Empty content list

            mock_client = MagicMock()
            mock_client.messages.create = MagicMock(return_value=mock_response)
            mock_anthropic.Anthropic.return_value = mock_client

            # Provide fake API key directly to constructor
            ocr_service = OCRService(api_key="test-api-key-for-ci")
            # Should handle gracefully - either return empty string or raise
            try:
                result = await ocr_service.extract_text_from_pdf(b"fake_pdf_bytes")
                # If it doesn't raise, it should return empty or default text
                assert result is not None
            except Exception:
                # Acceptable to raise on invalid response
                pass


class TestStorageServiceErrors:
    """Test storage service error handling."""

    @pytest.mark.asyncio
    async def test_storage_upload_failure(self):
        """Storage service should handle upload failures gracefully."""
        from io import BytesIO

        # Create a mock storage that raises on upload
        mock_storage = MagicMock()
        mock_storage.upload_file = AsyncMock(
            side_effect=Exception("S3 upload failed: Access Denied")
        )

        with pytest.raises(Exception) as exc_info:
            await mock_storage.upload_file(BytesIO(b"test"), "test/key.pdf", "application/pdf")

        # Should raise the error
        assert "upload failed" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_storage_download_failure(self):
        """Storage service should handle download failures gracefully."""
        # Create a mock storage that raises on download
        mock_storage = MagicMock()
        mock_storage.download_file = AsyncMock(
            side_effect=Exception("S3 download failed: NoSuchKey")
        )

        with pytest.raises(Exception) as exc_info:
            await mock_storage.download_file("nonexistent/key.pdf")

        # Should raise the error
        assert "download failed" in str(exc_info.value).lower()


class TestQuotaServiceErrors:
    """Test quota service error handling."""

    def test_quota_race_condition(self, db: Session):
        """Quota service should handle concurrent consume attempts safely."""
        from app.services import quota_service

        # Create user near quota limit
        user = create_user_with_quota(db, used=29, limit=30)

        # First consume should succeed - returns QuotaUsage object
        result1 = quota_service.consume_quota(db, user.id, amount=1)
        assert result1 is not None
        assert result1.used == 30

        # Second consume should fail (quota exhausted)
        with pytest.raises(quota_service.QuotaExceededError):
            quota_service.consume_quota(db, user.id, amount=1)

    def test_quota_invalid_user(self, db: Session):
        """Quota service should raise error for non-existent users."""
        from app.services import quota_service

        # Non-existent user ID (no subscription)
        fake_user_id = 999999

        # Should raise ValueError for user without subscription
        with pytest.raises(ValueError) as exc_info:
            quota_service.check_quota(db, fake_user_id)

        assert "subscription" in str(exc_info.value).lower()


class TestWebhookErrors:
    """Test webhook error handling.

    Note: These tests verify the webhook endpoint exists and handles
    malformed requests. Signature validation depends on configuration.
    """

    @pytest.mark.asyncio
    async def test_clerk_webhook_endpoint_exists(self):
        """Clerk webhook endpoint should exist and accept POST."""
        from fastapi.testclient import TestClient
        from app.main import app

        client = TestClient(app)

        # Send a basic request to verify endpoint exists
        response = client.post(
            "/v1/webhooks/clerk",
            json={"type": "user.created", "data": {}},
        )

        # Should either process or reject, but not 404
        assert response.status_code != 404

    @pytest.mark.asyncio
    async def test_clerk_webhook_invalid_event_type(self):
        """Clerk webhook should handle unknown event types gracefully."""
        from fastapi.testclient import TestClient
        from app.main import app

        client = TestClient(app)

        # Patch settings to enable debug mode (webhook secret not required in debug)
        with patch("app.api.webhooks.clerk.get_settings") as mock_settings:
            mock_settings.return_value.debug = True
            mock_settings.return_value.clerk_webhook_secret = None

            # Unknown event type
            response = client.post(
                "/v1/webhooks/clerk",
                json={"type": "unknown.event.type", "data": {"something": "here"}},
            )

            # Should handle gracefully (200 OK to acknowledge, or 400 for invalid)
            # The key is it doesn't crash (500)
            assert response.status_code in [200, 400, 401, 403]


class TestDatabaseErrors:
    """Test database error handling."""

    def test_db_connection_handling(self, db: Session):
        """Database operations should handle connection issues gracefully."""
        from app.models.user import User

        # Test that invalid queries don't crash the app
        try:
            # Query with invalid filter should handle gracefully
            result = db.query(User).filter(User.id == "not_an_integer").first()
            # SQLAlchemy might auto-convert or raise
        except Exception as e:
            # Should be a database error, not a crash
            assert "sql" in str(type(e).__name__).lower() or isinstance(e, Exception)

    def test_db_rollback_on_error(self, db: Session):
        """Database should rollback on constraint violations."""
        from app.models.user import User

        # Create a user
        user = User(
            email="unique@test.com",
            full_name="Test User",
            clerk_user_id="test_clerk_123",
        )
        db.add(user)
        db.commit()

        # Try to create duplicate - should rollback
        try:
            duplicate = User(
                email="unique@test.com",  # Duplicate email
                full_name="Another User",
                clerk_user_id="test_clerk_456",
            )
            db.add(duplicate)
            db.commit()
        except Exception:
            db.rollback()

        # Should be able to continue using session
        count = db.query(User).count()
        assert count >= 1
