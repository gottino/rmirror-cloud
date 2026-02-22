"""Tests for the Umami analytics utility."""

from unittest.mock import AsyncMock, patch

import pytest

from app.utils.umami import track_event


@pytest.fixture(autouse=True)
def _reset_client():
    """Reset the module-level httpx client between tests."""
    import app.utils.umami as mod
    mod._client = None
    yield
    mod._client = None


class TestTrackEvent:
    """Tests for the track_event function."""

    @pytest.mark.asyncio
    async def test_noop_when_not_configured(self):
        """Should silently no-op when Umami is not configured."""
        with patch("app.utils.umami.get_settings") as mock_settings:
            mock_settings.return_value.umami_url = None
            mock_settings.return_value.umami_website_id = None

            # Should not raise
            await track_event("test_event", {"key": "value"})

    @pytest.mark.asyncio
    async def test_noop_when_url_missing(self):
        """Should no-op when only website_id is set."""
        with patch("app.utils.umami.get_settings") as mock_settings:
            mock_settings.return_value.umami_url = None
            mock_settings.return_value.umami_website_id = "abc123"

            await track_event("test_event")

    @pytest.mark.asyncio
    async def test_sends_event_when_configured(self):
        """Should POST to Umami when both URL and website ID are set."""
        mock_response = AsyncMock()
        mock_client = AsyncMock()
        mock_client.post = mock_response

        with (
            patch("app.utils.umami.get_settings") as mock_settings,
            patch("app.utils.umami._get_client", return_value=mock_client),
        ):
            mock_settings.return_value.umami_url = "https://umami.example.com"
            mock_settings.return_value.umami_website_id = "site-123"

            await track_event("account_created", {"is_beta": True}, user_id=42)

            mock_response.assert_called_once()
            call_args = mock_response.call_args
            assert call_args[0][0] == "https://umami.example.com/api/send"

            payload = call_args[1]["json"]
            assert payload["type"] == "event"
            assert payload["payload"]["website"] == "site-123"
            assert payload["payload"]["url"] == "/api/backend"
            assert payload["payload"]["name"] == "account_created"
            assert payload["payload"]["data"]["is_beta"] is True
            assert payload["payload"]["data"]["user_id"] == 42

    @pytest.mark.asyncio
    async def test_sends_event_without_data(self):
        """Should send event without data when none provided."""
        mock_response = AsyncMock()
        mock_client = AsyncMock()
        mock_client.post = mock_response

        with (
            patch("app.utils.umami.get_settings") as mock_settings,
            patch("app.utils.umami._get_client", return_value=mock_client),
        ):
            mock_settings.return_value.umami_url = "https://umami.example.com"
            mock_settings.return_value.umami_website_id = "site-123"

            await track_event("account_deleted")

            payload = mock_response.call_args[1]["json"]
            assert payload["payload"]["name"] == "account_deleted"
            assert "data" not in payload["payload"]

    @pytest.mark.asyncio
    async def test_sends_user_id_without_data(self):
        """Should create data dict for user_id when no other data provided."""
        mock_response = AsyncMock()
        mock_client = AsyncMock()
        mock_client.post = mock_response

        with (
            patch("app.utils.umami.get_settings") as mock_settings,
            patch("app.utils.umami._get_client", return_value=mock_client),
        ):
            mock_settings.return_value.umami_url = "https://umami.example.com"
            mock_settings.return_value.umami_website_id = "site-123"

            await track_event("account_deleted", user_id=7)

            payload = mock_response.call_args[1]["json"]
            assert payload["payload"]["data"] == {"user_id": 7}

    @pytest.mark.asyncio
    async def test_never_raises_on_network_error(self):
        """Should swallow exceptions from HTTP failures."""
        mock_client = AsyncMock()
        mock_client.post.side_effect = Exception("Connection refused")

        with (
            patch("app.utils.umami.get_settings") as mock_settings,
            patch("app.utils.umami._get_client", return_value=mock_client),
        ):
            mock_settings.return_value.umami_url = "https://umami.example.com"
            mock_settings.return_value.umami_website_id = "site-123"

            # Should not raise
            await track_event("test_event", {"key": "value"})

    @pytest.mark.asyncio
    async def test_strips_trailing_slash_from_url(self):
        """Should handle trailing slash in umami_url."""
        mock_response = AsyncMock()
        mock_client = AsyncMock()
        mock_client.post = mock_response

        with (
            patch("app.utils.umami.get_settings") as mock_settings,
            patch("app.utils.umami._get_client", return_value=mock_client),
        ):
            mock_settings.return_value.umami_url = "https://umami.example.com/"
            mock_settings.return_value.umami_website_id = "site-123"

            await track_event("test")

            call_url = mock_response.call_args[0][0]
            assert call_url == "https://umami.example.com/api/send"
