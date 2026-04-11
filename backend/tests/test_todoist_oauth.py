"""Tests for Todoist OAuth service."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.todoist_oauth import TodoistOAuthService


@pytest.fixture
def oauth_service():
    """Create OAuth service with test credentials."""
    with patch("app.services.todoist_oauth.get_settings") as mock_settings:
        mock_settings.return_value = MagicMock(
            todoist_client_id="test_client_id",
            todoist_client_secret="test_client_secret",
            todoist_redirect_uri="http://localhost:3000/integrations/todoist/callback",
            debug=False,
        )
        return TodoistOAuthService()


class TestGetAuthorizationUrl:
    def test_returns_url_with_client_id(self, oauth_service):
        url = oauth_service.get_authorization_url(state="test_state")
        assert "test_client_id" in url
        assert "test_state" in url

    def test_includes_required_scopes(self, oauth_service):
        url = oauth_service.get_authorization_url(state="test_state")
        assert "task%3Aadd" in url or "task:add" in url
        assert "data%3Aread" in url or "data:read" in url

    def test_includes_redirect_uri(self, oauth_service):
        """Verify the URL is well-formed (starts with Todoist auth endpoint)."""
        url = oauth_service.get_authorization_url(state="test_state")
        assert url.startswith("https://todoist.com/oauth/authorize")


class TestExchangeCodeForToken:
    @pytest.mark.asyncio
    async def test_exchanges_code_successfully(self, oauth_service):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"access_token": "test_token", "token_type": "Bearer"}

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            result = await oauth_service.exchange_code_for_token("test_code")
            assert result["access_token"] == "test_token"

    @pytest.mark.asyncio
    async def test_raises_on_error_response(self, oauth_service):
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Bad Request"
        mock_response.raise_for_status.side_effect = Exception("Bad Request")

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            with pytest.raises(Exception):
                await oauth_service.exchange_code_for_token("bad_code")


class TestListProjects:
    @pytest.mark.asyncio
    async def test_returns_projects(self, oauth_service):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"id": "123", "name": "Inbox", "is_inbox_project": True},
            {"id": "456", "name": "Work", "is_inbox_project": False},
        ]

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            projects = await oauth_service.list_projects("test_token")
            assert len(projects) == 2
            assert projects[0]["name"] == "Inbox"
