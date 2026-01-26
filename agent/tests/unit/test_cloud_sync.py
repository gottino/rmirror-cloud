"""
Unit tests for cloud_sync module.
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.sync.cloud_sync import (
    CloudSync,
    CloudSyncError,
    QuotaExceededError,
    RateLimitError,
)


class TestExceptions:
    """Test exception classes."""

    def test_cloud_sync_error(self):
        """Test CloudSyncError exception."""
        error = CloudSyncError("Test error message")
        assert str(error) == "Test error message"

    def test_rate_limit_error_with_retry_after(self):
        """Test RateLimitError with retry_after."""
        error = RateLimitError("Rate limited", retry_after=30)
        assert str(error) == "Rate limited"
        assert error.retry_after == 30

    def test_rate_limit_error_default_retry_after(self):
        """Test RateLimitError uses default retry_after of 10."""
        error = RateLimitError("Rate limited")
        assert error.retry_after == 10

    def test_quota_exceeded_error_with_status(self):
        """Test QuotaExceededError with quota status."""
        quota_status = {"used": 30, "limit": 30, "reset_at": "2024-02-01"}
        error = QuotaExceededError("Quota exceeded", quota_status=quota_status)
        assert str(error) == "Quota exceeded"
        assert error.quota_status == quota_status

    def test_quota_exceeded_error_no_status(self):
        """Test QuotaExceededError without quota status."""
        error = QuotaExceededError("Quota exceeded")
        assert error.quota_status is None


class TestCloudSyncInit:
    """Test CloudSync initialization."""

    def test_init_creates_instance(self, test_config):
        """Test CloudSync initializes with config."""
        sync = CloudSync(test_config)
        assert sync.config == test_config
        assert sync.client is None
        assert sync.authenticated is False
        assert sync.user_email is None
        assert sync.user_id is None


class TestAuthentication:
    """Test authentication methods."""

    @pytest.mark.asyncio
    async def test_authenticate_with_valid_token(self, test_config_with_token):
        """Test authentication with a valid existing token."""
        sync = CloudSync(test_config_with_token)

        # Mock the HTTP client response for token validation
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        with patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response

            result = await sync.authenticate()

            assert result is True
            assert sync.authenticated is True

        await sync.close()

    @pytest.mark.asyncio
    async def test_authenticate_401_expired_token_clerk_auth(self, test_config_with_token):
        """Test authentication failure with expired token using Clerk auth."""
        test_config_with_token.api.use_clerk_auth = True
        sync = CloudSync(test_config_with_token)

        # Mock 401 response for expired token
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 401
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "401 Unauthorized",
            request=MagicMock(),
            response=mock_response
        )

        with patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response

            with pytest.raises(CloudSyncError, match="token expired"):
                await sync.authenticate()

        await sync.close()

    @pytest.mark.asyncio
    async def test_authenticate_with_password(self, test_config, mock_keychain):
        """Test authentication with email/password."""
        test_config.api.use_clerk_auth = False
        sync = CloudSync(test_config)

        # Mock successful login response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"access_token": "new-jwt-token"}

        with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            result = await sync.authenticate()

            assert result is True
            assert sync.authenticated is True
            assert test_config.api._token == "new-jwt-token"

        await sync.close()

    @pytest.mark.asyncio
    async def test_authenticate_invalid_credentials(self, test_config, mock_keychain):
        """Test authentication with invalid credentials."""
        test_config.api.use_clerk_auth = False
        sync = CloudSync(test_config)

        # Mock 401 response for invalid credentials
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 401
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "401 Unauthorized",
            request=MagicMock(),
            response=mock_response
        )

        with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            with pytest.raises(CloudSyncError, match="Invalid email or password"):
                await sync.authenticate()

        await sync.close()

    @pytest.mark.asyncio
    async def test_authenticate_no_credentials(self, test_config, mock_keychain):
        """Test authentication fails without credentials."""
        test_config.api.use_clerk_auth = False
        test_config.api.email = ""
        test_config.api.password = ""
        sync = CloudSync(test_config)

        with pytest.raises(CloudSyncError, match="credentials not configured"):
            await sync.authenticate()

        await sync.close()


class TestUploadFile:
    """Test file upload methods."""

    @pytest.mark.asyncio
    async def test_upload_file_401_re_authenticates(self, test_config_with_token, temp_remarkable_dir):
        """Test upload retries authentication on 401."""
        sync = CloudSync(test_config_with_token)
        sync.authenticated = True
        sync.client = httpx.AsyncClient(timeout=30.0)

        # Get a test .rm file
        rm_file = list((temp_remarkable_dir / "test-notebook-uuid-1234").glob("*.rm"))[0]

        call_count = 0

        async def mock_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First call fails with 401
                response = MagicMock(spec=httpx.Response)
                response.status_code = 401
                response.text = "Unauthorized"
                raise httpx.HTTPStatusError("401", request=MagicMock(), response=response)
            else:
                # Second call succeeds
                response = MagicMock()
                response.status_code = 200
                response.raise_for_status = MagicMock()
                response.json.return_value = {"success": True, "extracted_text": "Test OCR"}
                return response

        async def mock_re_auth():
            sync.authenticated = True
            test_config_with_token.api._token = "new-token"
            return True

        with patch.object(sync.client, "post", new=mock_post):
            with patch.object(sync, "authenticate", new=mock_re_auth):
                result = await sync.upload_file(rm_file, "test-notebook-uuid-1234", "rm")

                assert result["success"] is True
                assert call_count == 2  # First failed, second succeeded

        await sync.close()

    @pytest.mark.asyncio
    async def test_upload_file_402_quota_exceeded(self, test_config_with_token, temp_remarkable_dir):
        """Test upload raises QuotaExceededError on 402."""
        sync = CloudSync(test_config_with_token)
        sync.authenticated = True
        sync.client = httpx.AsyncClient(timeout=30.0)

        rm_file = list((temp_remarkable_dir / "test-notebook-uuid-1234").glob("*.rm"))[0]

        # Mock 402 response
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 402
        mock_response.text = '{"error": "quota_exceeded", "quota": {"used": 30, "limit": 30, "reset_at": "2024-02-01"}}'
        mock_response.json.return_value = {
            "error": "quota_exceeded",
            "quota": {"used": 30, "limit": 30, "reset_at": "2024-02-01"}
        }

        async def mock_post(*args, **kwargs):
            raise httpx.HTTPStatusError("402", request=MagicMock(), response=mock_response)

        with patch.object(sync.client, "post", new=mock_post):
            with pytest.raises(QuotaExceededError) as exc_info:
                await sync.upload_file(rm_file, "test-notebook-uuid-1234", "rm")

            assert exc_info.value.quota_status == {"used": 30, "limit": 30, "reset_at": "2024-02-01"}

        await sync.close()

    @pytest.mark.asyncio
    async def test_upload_file_429_rate_limited(self, test_config_with_token, temp_remarkable_dir):
        """Test upload raises RateLimitError on 429."""
        sync = CloudSync(test_config_with_token)
        sync.authenticated = True
        sync.client = httpx.AsyncClient(timeout=30.0)

        rm_file = list((temp_remarkable_dir / "test-notebook-uuid-1234").glob("*.rm"))[0]

        # Mock 429 response
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 429
        mock_response.text = "Rate limit exceeded"
        mock_response.headers = {"Retry-After": "60"}

        async def mock_post(*args, **kwargs):
            raise httpx.HTTPStatusError("429", request=MagicMock(), response=mock_response)

        with patch.object(sync.client, "post", new=mock_post):
            with pytest.raises(RateLimitError) as exc_info:
                await sync.upload_file(rm_file, "test-notebook-uuid-1234", "rm")

            assert exc_info.value.retry_after == 60

        await sync.close()

    @pytest.mark.asyncio
    async def test_upload_file_timeout(self, test_config_with_token, temp_remarkable_dir):
        """Test upload raises CloudSyncError on timeout."""
        sync = CloudSync(test_config_with_token)
        sync.authenticated = True
        sync.client = httpx.AsyncClient(timeout=30.0)

        rm_file = list((temp_remarkable_dir / "test-notebook-uuid-1234").glob("*.rm"))[0]

        async def mock_post(*args, **kwargs):
            raise httpx.TimeoutException("Connection timed out")

        with patch.object(sync.client, "post", new=mock_post):
            with pytest.raises(CloudSyncError, match="timeout"):
                await sync.upload_file(rm_file, "test-notebook-uuid-1234", "rm")

        await sync.close()

    @pytest.mark.asyncio
    async def test_upload_file_not_found(self, test_config_with_token):
        """Test upload raises CloudSyncError for missing file."""
        sync = CloudSync(test_config_with_token)
        sync.authenticated = True
        sync.client = httpx.AsyncClient(timeout=30.0)

        fake_path = Path("/nonexistent/file.rm")

        with pytest.raises(CloudSyncError, match="File not found"):
            await sync.upload_file(fake_path, "test-uuid", "rm")

        await sync.close()

    @pytest.mark.asyncio
    async def test_upload_skips_unknown_file_type(self, test_config_with_token, tmp_path):
        """Test upload skips unknown file types gracefully."""
        sync = CloudSync(test_config_with_token)
        sync.authenticated = True
        sync.client = httpx.AsyncClient(timeout=30.0)

        # Create a fake file
        fake_file = tmp_path / "test.unknown"
        fake_file.write_text("test content")

        result = await sync.upload_file(fake_file, "test-uuid", "unknown")

        assert result["success"] is True
        assert result.get("skipped") is True

        await sync.close()


class TestFormatQuotaDisplay:
    """Test quota display formatting."""

    def test_format_quota_display_active(self, test_config):
        """Test formatting active quota status."""
        sync = CloudSync(test_config)
        quota_data = {
            "used": 10,
            "limit": 30,
            "percentage_used": 33.33,
            "reset_at": "2024-02-01",
            "is_exhausted": False,
            "is_near_limit": False,
        }

        result = sync.format_quota_display(quota_data)

        assert "ACTIVE" in result
        assert "10/30" in result
        assert "33%" in result
        assert "20" in result  # Remaining

    def test_format_quota_display_near_limit(self, test_config):
        """Test formatting near-limit quota status."""
        sync = CloudSync(test_config)
        quota_data = {
            "used": 27,
            "limit": 30,
            "percentage_used": 90.0,
            "reset_at": "2024-02-01",
            "is_exhausted": False,
            "is_near_limit": True,
        }

        result = sync.format_quota_display(quota_data)

        assert "APPROACHING LIMIT" in result
        assert "27/30" in result

    def test_format_quota_display_exhausted(self, test_config):
        """Test formatting exhausted quota status."""
        sync = CloudSync(test_config)
        quota_data = {
            "used": 30,
            "limit": 30,
            "percentage_used": 100.0,
            "reset_at": "2024-02-01",
            "is_exhausted": True,
            "is_near_limit": True,
        }

        result = sync.format_quota_display(quota_data)

        assert "QUOTA EXCEEDED" in result
        assert "30/30" in result
        assert "0" in result  # Remaining


class TestLogout:
    """Test logout functionality."""

    def test_logout_clears_state(self, test_config_with_token, mock_keychain):
        """Test logout clears authentication state."""
        sync = CloudSync(test_config_with_token)
        sync.authenticated = True
        sync.user_email = "test@example.com"
        sync.user_id = 123

        sync.logout()

        assert sync.authenticated is False
        assert sync.user_email is None
        assert sync.user_id is None
        assert test_config_with_token.api._token is None


class TestMetadataParsing:
    """Test metadata file parsing."""

    def test_parse_metadata_file(self, test_config, temp_remarkable_dir):
        """Test parsing .metadata file."""
        sync = CloudSync(test_config)
        metadata_path = temp_remarkable_dir / "test-notebook-uuid-1234.metadata"

        result = sync._parse_metadata_file(metadata_path)

        assert result["notebook_uuid"] == "test-notebook-uuid-1234"
        assert result["visible_name"] == "Test Notebook"
        assert result["document_type"] == "notebook"
        assert "last_modified" in result

    def test_parse_metadata_folder_type(self, test_config, tmp_path):
        """Test parsing folder type metadata."""
        sync = CloudSync(test_config)

        # Create a folder metadata file
        metadata = {
            "visibleName": "Test Folder",
            "type": "CollectionType",
            "parent": "",
        }
        import json
        metadata_path = tmp_path / "folder-uuid.metadata"
        with open(metadata_path, "w") as f:
            json.dump(metadata, f)

        result = sync._parse_metadata_file(metadata_path)

        assert result["document_type"] == "folder"
        assert result["visible_name"] == "Test Folder"
