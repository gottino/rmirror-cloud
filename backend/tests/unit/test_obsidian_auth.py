"""Tests for Obsidian API key authentication."""

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.auth.dependencies import get_obsidian_user
from app.models.sync_record import IntegrationConfig
from app.models.user import User


@pytest.mark.asyncio
class TestGetObsidianUser:
    async def test_valid_api_key_returns_user(self):
        raw_key = "test-key-abc123"

        mock_user = MagicMock(spec=User)
        mock_user.id = 1
        mock_user.is_active = True

        mock_config = MagicMock(spec=IntegrationConfig)
        mock_config.user_id = 1
        mock_config.is_enabled = True

        mock_db = MagicMock()
        config_query = MagicMock()
        config_query.filter.return_value.first.return_value = mock_config
        user_query = MagicMock()
        user_query.filter.return_value.first.return_value = mock_user
        mock_db.query.side_effect = [config_query, user_query]

        mock_credentials = MagicMock()
        mock_credentials.credentials = raw_key

        user = await get_obsidian_user(mock_credentials, mock_db)
        assert user == mock_user

    async def test_invalid_api_key_raises_401(self):
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        mock_credentials = MagicMock()
        mock_credentials.credentials = "invalid-key"

        with pytest.raises(HTTPException) as exc_info:
            await get_obsidian_user(mock_credentials, mock_db)
        assert exc_info.value.status_code == 401

    async def test_disabled_integration_raises_403(self):
        raw_key = "test-key-abc123"

        mock_config = MagicMock(spec=IntegrationConfig)
        mock_config.user_id = 1
        mock_config.is_enabled = False

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_config

        mock_credentials = MagicMock()
        mock_credentials.credentials = raw_key

        with pytest.raises(HTTPException) as exc_info:
            await get_obsidian_user(mock_credentials, mock_db)
        assert exc_info.value.status_code == 403
