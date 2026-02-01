"""Unit tests for NotionOAuthService.

Tests cover:
- OAuth authorization URL generation
- Token exchange
- Database listing
- Database creation (with initial_data_source API)
- Database validation
- Property management
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx


class TestNotionOAuthServiceOAuthFlow:
    """Tests for OAuth flow methods."""

    def test_get_authorization_url_generates_valid_url(self, notion_oauth_settings):
        """Verify authorization URL contains required OAuth parameters."""
        with patch("app.services.notion_oauth.get_settings", return_value=notion_oauth_settings):
            from app.services.notion_oauth import NotionOAuthService

            service = NotionOAuthService()
            url = service.get_authorization_url(state="test-state-123")

            # Verify URL structure
            assert "https://api.notion.com/v1/oauth/authorize" in url
            assert "client_id=test-client-id" in url
            assert "redirect_uri=http%3A%2F%2Flocalhost%3A3000%2Fcallback" in url
            assert "state=test-state-123" in url
            assert "response_type=code" in url
            assert "owner=user" in url

    @pytest.mark.asyncio
    async def test_exchange_code_for_token_success(self, notion_oauth_settings, mock_httpx_async_client):
        """Test successful token exchange returns expected data."""
        with patch("app.services.notion_oauth.get_settings", return_value=notion_oauth_settings):
            from app.services.notion_oauth import NotionOAuthService

            service = NotionOAuthService()
            result = await service.exchange_code_for_token(code="test-auth-code")

            # Verify token data is extracted correctly
            assert result["access_token"] == "test-access-token"
            assert result["workspace_id"] == "ws-123"
            assert result["workspace_name"] == "Test Workspace"
            assert result["bot_id"] == "bot-123"
            assert result["owner"] == {"type": "user"}

    @pytest.mark.asyncio
    async def test_exchange_code_for_token_http_error(self, notion_oauth_settings):
        """Test error handling when token exchange fails."""
        with patch("app.services.notion_oauth.get_settings", return_value=notion_oauth_settings):
            with patch("httpx.AsyncClient") as mock_client_class:
                mock_instance = MagicMock()
                mock_response = MagicMock()
                mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
                    "Unauthorized",
                    request=MagicMock(),
                    response=MagicMock(status_code=401),
                )
                mock_instance.post = AsyncMock(return_value=mock_response)
                mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
                mock_instance.__aexit__ = AsyncMock(return_value=None)
                mock_client_class.return_value = mock_instance

                from app.services.notion_oauth import NotionOAuthService

                service = NotionOAuthService()

                with pytest.raises(httpx.HTTPStatusError):
                    await service.exchange_code_for_token(code="invalid-code")


class TestNotionOAuthServiceDatabaseListing:
    """Tests for database and page listing methods."""

    @pytest.mark.asyncio
    async def test_list_databases_returns_formatted_list(
        self, notion_oauth_settings, sample_notion_database_response
    ):
        """Test that list_databases returns properly formatted database list."""
        with patch("app.services.notion_oauth.get_settings", return_value=notion_oauth_settings):
            with patch("app.services.notion_oauth.NotionClient") as mock_client_class:
                mock_client = MagicMock()
                mock_client.search.return_value = {
                    "results": [sample_notion_database_response]
                }
                mock_client_class.return_value = mock_client

                from app.services.notion_oauth import NotionOAuthService

                service = NotionOAuthService()
                databases = await service.list_databases(access_token="test-token")

                assert len(databases) == 1
                assert databases[0]["id"] == "db-123"
                assert databases[0]["title"] == "Test Database"
                assert databases[0]["url"] == "https://notion.so/db-123"

    @pytest.mark.asyncio
    async def test_list_databases_handles_empty_results(self, notion_oauth_settings):
        """Test handling of empty database list."""
        with patch("app.services.notion_oauth.get_settings", return_value=notion_oauth_settings):
            with patch("app.services.notion_oauth.NotionClient") as mock_client_class:
                mock_client = MagicMock()
                mock_client.search.return_value = {"results": []}
                mock_client_class.return_value = mock_client

                from app.services.notion_oauth import NotionOAuthService

                service = NotionOAuthService()
                databases = await service.list_databases(access_token="test-token")

                assert databases == []

    @pytest.mark.asyncio
    async def test_list_pages_returns_formatted_list(
        self, notion_oauth_settings, sample_notion_page_response
    ):
        """Test that list_pages returns properly formatted page list."""
        with patch("app.services.notion_oauth.get_settings", return_value=notion_oauth_settings):
            with patch("app.services.notion_oauth.NotionClient") as mock_client_class:
                mock_client = MagicMock()
                mock_client.search.return_value = {
                    "results": [sample_notion_page_response]
                }
                mock_client_class.return_value = mock_client

                from app.services.notion_oauth import NotionOAuthService

                service = NotionOAuthService()
                pages = await service.list_pages(access_token="test-token")

                assert len(pages) == 1
                assert pages[0]["id"] == "page-123"
                assert pages[0]["title"] == "Test Page"


class TestNotionOAuthServiceDatabaseCreation:
    """Tests for database creation with initial_data_source API."""

    @pytest.mark.asyncio
    async def test_create_rmirror_database_todos_uses_workflow_not_status(
        self, notion_oauth_settings, mock_httpx_client
    ):
        """Verify todos database uses Workflow (select) instead of Status (status type)."""
        with patch("app.services.notion_oauth.get_settings", return_value=notion_oauth_settings):
            with patch("app.services.notion_oauth.NotionClient") as mock_client_class:
                mock_client = MagicMock()
                mock_client.pages.create.return_value = {"id": "parent-page-123"}
                mock_client_class.return_value = mock_client

                with patch("app.services.notion_oauth.httpx.Client") as mock_http_class:
                    mock_http = MagicMock()
                    mock_response = MagicMock()
                    mock_response.json.return_value = {
                        "id": "db-todos-123",
                        "url": "https://notion.so/db-todos-123",
                        "created_time": "2026-01-01T00:00:00.000Z",
                    }
                    mock_response.raise_for_status.return_value = None
                    mock_http.post.return_value = mock_response
                    mock_http.close.return_value = None
                    mock_http_class.return_value = mock_http

                    from app.services.notion_oauth import NotionOAuthService

                    service = NotionOAuthService()
                    result = await service.create_rmirror_database(
                        access_token="test-token",
                        database_title="rMirror Todos",
                        database_type="todos",
                    )

                    # Verify the API call was made with Workflow property
                    call_args = mock_http.post.call_args
                    json_body = call_args.kwargs["json"]
                    properties = json_body["initial_data_source"]["properties"]

                    # Should have Workflow (select), not Status (status type)
                    assert "Workflow" in properties
                    assert properties["Workflow"]["select"]["options"][0]["name"] == "Not started"
                    assert "Status" not in properties  # Status is NOT used for todos

                    assert result["database_id"] == "db-todos-123"
                    assert result["type"] == "todos"

    @pytest.mark.asyncio
    async def test_create_rmirror_database_uses_initial_data_source(
        self, notion_oauth_settings
    ):
        """Verify database creation uses initial_data_source.properties per API 2025-09-03."""
        with patch("app.services.notion_oauth.get_settings", return_value=notion_oauth_settings):
            with patch("app.services.notion_oauth.NotionClient") as mock_client_class:
                mock_client = MagicMock()
                mock_client.pages.create.return_value = {"id": "parent-page-123"}
                mock_client_class.return_value = mock_client

                with patch("app.services.notion_oauth.httpx.Client") as mock_http_class:
                    mock_http = MagicMock()
                    mock_response = MagicMock()
                    mock_response.json.return_value = {
                        "id": "db-123",
                        "url": "https://notion.so/db-123",
                        "created_time": "2026-01-01T00:00:00.000Z",
                    }
                    mock_response.raise_for_status.return_value = None
                    mock_http.post.return_value = mock_response
                    mock_http.close.return_value = None
                    mock_http_class.return_value = mock_http

                    from app.services.notion_oauth import NotionOAuthService

                    service = NotionOAuthService()
                    await service.create_rmirror_database(
                        access_token="test-token",
                        database_title="Test DB",
                        database_type="notebooks",
                    )

                    # Verify API call structure
                    call_args = mock_http.post.call_args
                    json_body = call_args.kwargs["json"]

                    # Must use initial_data_source wrapper
                    assert "initial_data_source" in json_body
                    assert "properties" in json_body["initial_data_source"]

                    # Verify API version header
                    headers = call_args.kwargs["headers"]
                    assert headers["Notion-Version"] == "2025-09-03"

    @pytest.mark.asyncio
    async def test_create_rmirror_database_notebooks_schema(self, notion_oauth_settings):
        """Verify notebooks database has correct property schema."""
        with patch("app.services.notion_oauth.get_settings", return_value=notion_oauth_settings):
            with patch("app.services.notion_oauth.NotionClient") as mock_client_class:
                mock_client = MagicMock()
                mock_client.pages.create.return_value = {"id": "parent-page-123"}
                mock_client_class.return_value = mock_client

                with patch("app.services.notion_oauth.httpx.Client") as mock_http_class:
                    mock_http = MagicMock()
                    mock_response = MagicMock()
                    mock_response.json.return_value = {
                        "id": "db-notebooks-123",
                        "url": "https://notion.so/db-notebooks-123",
                        "created_time": "2026-01-01T00:00:00.000Z",
                    }
                    mock_response.raise_for_status.return_value = None
                    mock_http.post.return_value = mock_response
                    mock_http.close.return_value = None
                    mock_http_class.return_value = mock_http

                    from app.services.notion_oauth import NotionOAuthService

                    service = NotionOAuthService()
                    result = await service.create_rmirror_database(
                        access_token="test-token",
                        database_title="rMirror Notebooks",
                        database_type="notebooks",
                    )

                    call_args = mock_http.post.call_args
                    json_body = call_args.kwargs["json"]
                    properties = json_body["initial_data_source"]["properties"]

                    # Verify notebooks schema has expected properties
                    assert "Name" in properties
                    assert properties["Name"] == {"title": {}}
                    assert "UUID" in properties
                    assert "Path" in properties
                    assert "Tags" in properties
                    assert "Pages" in properties
                    assert "Last Opened" in properties
                    assert "Last Modified" in properties
                    assert "Synced At" in properties
                    assert "Status" in properties  # Notebooks use Status (select)

    @pytest.mark.asyncio
    async def test_create_rmirror_database_creates_parent_page_if_none(
        self, notion_oauth_settings
    ):
        """Test that parent page is created when no parent_page_id provided."""
        with patch("app.services.notion_oauth.get_settings", return_value=notion_oauth_settings):
            with patch("app.services.notion_oauth.NotionClient") as mock_client_class:
                mock_client = MagicMock()
                mock_client.pages.create.return_value = {"id": "auto-parent-page"}
                mock_client_class.return_value = mock_client

                with patch("app.services.notion_oauth.httpx.Client") as mock_http_class:
                    mock_http = MagicMock()
                    mock_response = MagicMock()
                    mock_response.json.return_value = {
                        "id": "db-123",
                        "url": "https://notion.so/db-123",
                        "created_time": "2026-01-01T00:00:00.000Z",
                    }
                    mock_response.raise_for_status.return_value = None
                    mock_http.post.return_value = mock_response
                    mock_http.close.return_value = None
                    mock_http_class.return_value = mock_http

                    from app.services.notion_oauth import NotionOAuthService

                    service = NotionOAuthService()
                    await service.create_rmirror_database(
                        access_token="test-token",
                        parent_page_id=None,  # No parent provided
                        database_title="Test DB",
                    )

                    # Verify parent page was created
                    mock_client.pages.create.assert_called_once()
                    page_create_call = mock_client.pages.create.call_args
                    assert page_create_call.kwargs["parent"] == {"type": "workspace", "workspace": True}

    @pytest.mark.asyncio
    async def test_create_rmirror_database_http_error_handling(self, notion_oauth_settings):
        """Test HTTP error handling during database creation."""
        with patch("app.services.notion_oauth.get_settings", return_value=notion_oauth_settings):
            with patch("app.services.notion_oauth.NotionClient") as mock_client_class:
                mock_client = MagicMock()
                mock_client.pages.create.return_value = {"id": "parent-page-123"}
                mock_client_class.return_value = mock_client

                with patch("app.services.notion_oauth.httpx.Client") as mock_http_class:
                    mock_http = MagicMock()
                    mock_response = MagicMock()
                    mock_response.text = "Validation error: invalid properties"
                    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
                        "Bad Request",
                        request=MagicMock(),
                        response=mock_response,
                    )
                    mock_http.post.return_value = mock_response
                    mock_http.close.return_value = None
                    mock_http_class.return_value = mock_http

                    from app.services.notion_oauth import NotionOAuthService

                    service = NotionOAuthService()

                    with pytest.raises(Exception) as exc_info:
                        await service.create_rmirror_database(
                            access_token="test-token",
                            database_title="Test DB",
                        )

                    assert "Failed to create Notion database" in str(exc_info.value)


class TestNotionOAuthServiceDatabaseValidation:
    """Tests for database validation methods."""

    @pytest.mark.asyncio
    async def test_validate_database_returns_true_for_valid(self, notion_oauth_settings):
        """Test validation returns True for accessible database."""
        with patch("app.services.notion_oauth.get_settings", return_value=notion_oauth_settings):
            with patch("app.services.notion_oauth.NotionClient") as mock_client_class:
                mock_client = MagicMock()
                mock_client.databases.retrieve.return_value = {"id": "db-123"}
                mock_client_class.return_value = mock_client

                from app.services.notion_oauth import NotionOAuthService

                service = NotionOAuthService()
                result = await service.validate_database(
                    access_token="test-token",
                    database_id="db-123",
                )

                assert result is True
                mock_client.databases.retrieve.assert_called_once_with(database_id="db-123")

    @pytest.mark.asyncio
    async def test_validate_database_returns_false_for_invalid(self, notion_oauth_settings):
        """Test validation returns False when database is not accessible."""
        with patch("app.services.notion_oauth.get_settings", return_value=notion_oauth_settings):
            with patch("app.services.notion_oauth.NotionClient") as mock_client_class:
                mock_client = MagicMock()
                mock_client.databases.retrieve.side_effect = Exception("Database not found")
                mock_client_class.return_value = mock_client

                from app.services.notion_oauth import NotionOAuthService

                service = NotionOAuthService()
                result = await service.validate_database(
                    access_token="test-token",
                    database_id="invalid-db",
                )

                assert result is False

    @pytest.mark.asyncio
    async def test_get_database_info_returns_properties(
        self, notion_oauth_settings, sample_notion_database_response
    ):
        """Test get_database_info returns complete database info."""
        with patch("app.services.notion_oauth.get_settings", return_value=notion_oauth_settings):
            with patch("app.services.notion_oauth.NotionClient") as mock_client_class:
                mock_client = MagicMock()
                mock_client.databases.retrieve.return_value = sample_notion_database_response
                mock_client_class.return_value = mock_client

                from app.services.notion_oauth import NotionOAuthService

                service = NotionOAuthService()
                result = await service.get_database_info(
                    access_token="test-token",
                    database_id="db-123",
                )

                assert result is not None
                assert result["database_id"] == "db-123"
                assert result["title"] == "Test Database"
                assert "properties" in result
                assert "data_sources" in result


class TestNotionOAuthServicePropertyManagement:
    """Tests for database property management."""

    @pytest.mark.asyncio
    async def test_add_database_properties_todos_uses_workflow(self, notion_oauth_settings):
        """Verify adding properties to todos database uses Workflow (select)."""
        with patch("app.services.notion_oauth.get_settings", return_value=notion_oauth_settings):
            with patch("app.services.notion_oauth.NotionClient") as mock_client_class:
                mock_client = MagicMock()
                mock_client.databases.retrieve.return_value = {
                    "id": "db-123",
                    "data_sources": [{"id": "ds-456"}],
                }
                mock_client_class.return_value = mock_client

                with patch("app.services.notion_oauth.httpx.Client") as mock_http_class:
                    mock_http = MagicMock()
                    mock_response = MagicMock()
                    mock_response.json.return_value = {
                        "id": "ds-456",
                        "properties": {"Workflow": {}, "Completed": {}},
                    }
                    mock_response.raise_for_status.return_value = None
                    mock_http.patch.return_value = mock_response
                    mock_http.close.return_value = None
                    mock_http_class.return_value = mock_http

                    from app.services.notion_oauth import NotionOAuthService

                    service = NotionOAuthService()
                    result = await service.add_database_properties(
                        access_token="test-token",
                        database_id="db-123",
                        database_type="todos",
                    )

                    # Verify PATCH call includes Workflow property
                    call_args = mock_http.patch.call_args
                    json_body = call_args.kwargs["json"]
                    properties = json_body["properties"]

                    assert "Workflow" in properties
                    assert "Status" not in properties  # Should not have Status for todos

                    assert result["success"] is True
                    assert result["data_source_id"] == "ds-456"

    @pytest.mark.asyncio
    async def test_add_database_properties_retrieves_data_source_id(self, notion_oauth_settings):
        """Test that add_database_properties correctly retrieves data source ID."""
        with patch("app.services.notion_oauth.get_settings", return_value=notion_oauth_settings):
            with patch("app.services.notion_oauth.NotionClient") as mock_client_class:
                mock_client = MagicMock()
                mock_client.databases.retrieve.return_value = {
                    "id": "db-123",
                    "data_sources": [{"id": "my-data-source-id"}],
                }
                mock_client_class.return_value = mock_client

                with patch("app.services.notion_oauth.httpx.Client") as mock_http_class:
                    mock_http = MagicMock()
                    mock_response = MagicMock()
                    mock_response.json.return_value = {"id": "my-data-source-id", "properties": {}}
                    mock_response.raise_for_status.return_value = None
                    mock_http.patch.return_value = mock_response
                    mock_http.close.return_value = None
                    mock_http_class.return_value = mock_http

                    from app.services.notion_oauth import NotionOAuthService

                    service = NotionOAuthService()
                    result = await service.add_database_properties(
                        access_token="test-token",
                        database_id="db-123",
                        database_type="notebooks",
                    )

                    # Verify data source endpoint was called with correct ID
                    call_args = mock_http.patch.call_args
                    assert "my-data-source-id" in call_args.args[0]

    @pytest.mark.asyncio
    async def test_add_database_properties_no_data_source_error(self, notion_oauth_settings):
        """Test error when database has no data sources."""
        with patch("app.services.notion_oauth.get_settings", return_value=notion_oauth_settings):
            with patch("app.services.notion_oauth.NotionClient") as mock_client_class:
                mock_client = MagicMock()
                mock_client.databases.retrieve.return_value = {
                    "id": "db-123",
                    "data_sources": [],  # Empty data sources
                }
                mock_client_class.return_value = mock_client

                from app.services.notion_oauth import NotionOAuthService

                service = NotionOAuthService()

                with pytest.raises(Exception) as exc_info:
                    await service.add_database_properties(
                        access_token="test-token",
                        database_id="db-123",
                        database_type="notebooks",
                    )

                assert "No data sources found" in str(exc_info.value)
