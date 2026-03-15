"""Tests for Obsidian API helper functions."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.api.obsidian import _disable_obsidian, _enable_obsidian, _regenerate_key


class TestEnableObsidian:
    """Tests for _enable_obsidian helper."""

    @patch("app.api.obsidian.hash_api_key")
    @patch("app.api.obsidian.generate_api_key")
    @patch("app.api.obsidian.IntegrationConfig")
    def test_creates_config_and_returns_key(
        self, mock_integration_config, mock_generate, mock_hash
    ):
        mock_generate.return_value = "test-api-key-123"
        mock_hash.return_value = "hashed-key"

        mock_user = MagicMock()
        mock_user.id = 1
        mock_db = MagicMock()

        # No existing config
        mock_db.query.return_value.filter.return_value.first.return_value = None

        mock_config_instance = MagicMock()
        mock_integration_config.return_value = mock_config_instance

        result = _enable_obsidian(mock_user, mock_db)

        assert result.api_key == "test-api-key-123"
        assert result.enabled is True
        mock_config_instance.set_config.assert_called_once_with(
            {"base_folder": "rMirror"}
        )
        mock_db.add.assert_called_once_with(mock_config_instance)
        mock_db.commit.assert_called_once()

    def test_raises_400_when_already_exists(self):
        mock_user = MagicMock()
        mock_user.id = 1
        mock_db = MagicMock()

        # Existing config found
        mock_db.query.return_value.filter.return_value.first.return_value = MagicMock()

        with pytest.raises(HTTPException) as exc_info:
            _enable_obsidian(mock_user, mock_db)
        assert exc_info.value.status_code == 400


class TestRegenerateKey:
    """Tests for _regenerate_key helper."""

    @patch("app.api.obsidian.hash_api_key")
    @patch("app.api.obsidian.generate_api_key")
    def test_returns_new_key(self, mock_generate, mock_hash):
        mock_generate.return_value = "new-key-456"
        mock_hash.return_value = "new-hash"

        mock_user = MagicMock()
        mock_user.id = 1
        mock_db = MagicMock()

        mock_config = MagicMock()
        mock_config.is_enabled = True
        mock_db.query.return_value.filter.return_value.first.return_value = mock_config

        result = _regenerate_key(mock_user, mock_db)

        assert result.api_key == "new-key-456"
        assert result.enabled is True
        assert mock_config.api_key_hash == "new-hash"
        mock_db.commit.assert_called_once()

    def test_raises_404_when_not_found(self):
        mock_user = MagicMock()
        mock_user.id = 1
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            _regenerate_key(mock_user, mock_db)
        assert exc_info.value.status_code == 404


class TestDisableObsidian:
    """Tests for _disable_obsidian helper."""

    def test_sets_enabled_false_and_clears_hash(self):
        mock_user = MagicMock()
        mock_user.id = 1
        mock_db = MagicMock()

        mock_config = MagicMock()
        mock_config.is_enabled = True
        mock_config.api_key_hash = "some-hash"
        mock_db.query.return_value.filter.return_value.first.return_value = mock_config

        result = _disable_obsidian(mock_user, mock_db)

        assert mock_config.is_enabled is False
        assert mock_config.api_key_hash is None
        assert result["success"] is True
        mock_db.commit.assert_called_once()

    def test_raises_404_when_not_found(self):
        mock_user = MagicMock()
        mock_user.id = 1
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            _disable_obsidian(mock_user, mock_db)
        assert exc_info.value.status_code == 404
