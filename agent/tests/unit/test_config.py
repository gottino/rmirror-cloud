"""
Unit tests for configuration module.
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from app.config import (
    APIConfig,
    Config,
    ReMarkableConfig,
    SyncConfig,
    TrayConfig,
    WebConfig,
)


class TestAPIConfig:
    """Test API configuration."""

    def test_default_values(self, mock_keychain):
        """Test API config has sensible defaults."""
        config = APIConfig()

        assert config.url == "https://rmirror.io/api/v1"
        assert config.use_clerk_auth is True
        assert config.email == ""
        assert config.password == ""

    def test_token_property_returns_keychain_token(self, mock_keychain):
        """Test token property retrieves from keychain."""
        mock_keychain.get_token.return_value = "keychain-token"
        config = APIConfig()

        # When no in-memory token, should get from keychain
        token = config.token

        assert token == "keychain-token"
        mock_keychain.get_token.assert_called()

    def test_token_property_prefers_memory(self, mock_keychain):
        """Test token property prefers in-memory token."""
        mock_keychain.get_token.return_value = "keychain-token"
        config = APIConfig()
        config._token = "memory-token"

        token = config.token

        assert token == "memory-token"

    def test_token_setter_stores_in_keychain(self, mock_keychain):
        """Test token setter stores in keychain."""
        config = APIConfig()

        config.token = "new-token"

        assert config._token == "new-token"
        mock_keychain.store_token.assert_called_with("new-token")

    def test_clear_token(self, mock_keychain):
        """Test clear_token removes from memory and keychain."""
        config = APIConfig()
        config._token = "test-token"

        config.clear_token()

        assert config._token is None
        mock_keychain.delete_token.assert_called()


class TestReMarkableConfig:
    """Test reMarkable configuration."""

    def test_default_source_directory(self):
        """Test default reMarkable source directory."""
        config = ReMarkableConfig()

        # Should be the reMarkable Desktop app sync folder
        assert "remarkable/desktop" in str(config.source_directory)

    def test_path_expansion(self):
        """Test path expansion for tilde."""
        config = ReMarkableConfig(source_directory="~/remarkable")

        assert str(config.source_directory).startswith("/")
        assert "~" not in str(config.source_directory)


class TestWebConfig:
    """Test web UI configuration."""

    def test_default_values(self):
        """Test web config defaults."""
        config = WebConfig()

        assert config.enabled is True
        assert config.port == 5555
        assert config.host == "127.0.0.1"
        assert config.auto_launch_browser is True
        assert config.app_mode is True


class TestSyncConfig:
    """Test sync configuration."""

    def test_default_values(self):
        """Test sync config defaults."""
        config = SyncConfig()

        assert config.auto_sync is True
        assert config.batch_size == 10
        assert config.retry_attempts == 3
        assert config.sync_interval == 60
        assert config.cooldown_seconds == 5
        assert config.sync_all_notebooks is True
        assert config.max_pages_per_notebook is None

    def test_selected_notebooks_default_empty(self):
        """Test selected_notebooks defaults to empty list."""
        config = SyncConfig()

        assert config.selected_notebooks == []


class TestConfigLoadSave:
    """Test configuration loading and saving."""

    def test_load_from_yaml(self, temp_config_file, mock_keychain):
        """Test loading config from YAML file."""
        config = Config.from_yaml(temp_config_file)

        assert config.api.url == "http://localhost:8000/api/v1"
        assert config.api.email == "test@example.com"
        assert config.api.use_clerk_auth is False
        assert config.remarkable.watch_enabled is False
        assert config.web.enabled is False
        assert config.sync.auto_sync is False

    def test_load_nonexistent_file_raises(self, mock_keychain):
        """Test loading from nonexistent file raises error."""
        with pytest.raises(FileNotFoundError):
            Config.from_yaml(Path("/nonexistent/config.yaml"))

    def test_save_creates_file(self, tmp_path, mock_keychain):
        """Test saving config creates YAML file."""
        config = Config(
            api=APIConfig(
                url="http://test.example.com/api/v1",
                use_clerk_auth=False,
            ),
            sync=SyncConfig(auto_sync=False),
        )
        config_path = tmp_path / "saved_config.yaml"

        config.save(config_path)

        assert config_path.exists()

        # Verify content
        with open(config_path) as f:
            import yaml
            saved = yaml.safe_load(f)

        assert saved["api"]["url"] == "http://test.example.com/api/v1"
        assert saved["sync"]["auto_sync"] is False

    def test_save_excludes_token(self, tmp_path, mock_keychain):
        """Test saving config excludes token from file."""
        config = Config()
        config.api._token = "secret-token"
        config_path = tmp_path / "saved_config.yaml"

        config.save(config_path)

        with open(config_path) as f:
            content = f.read()

        assert "secret-token" not in content
        assert "token" not in content

    def test_save_creates_parent_directories(self, tmp_path, mock_keychain):
        """Test saving config creates parent directories."""
        config = Config()
        config_path = tmp_path / "nested" / "dir" / "config.yaml"

        config.save(config_path)

        assert config_path.exists()

    def test_load_missing_file_uses_defaults(self, tmp_path, mock_keychain):
        """Test loading from missing file uses defaults."""
        with patch.object(Config, "get_default_config_path", return_value=tmp_path / "nonexistent.yaml"):
            config = Config.load()

        # Should use defaults
        assert config.api.url == "https://rmirror.io/api/v1"
        assert config.sync.auto_sync is True


class TestConfigDefaultPath:
    """Test default config path detection."""

    def test_get_default_config_path_returns_existing(self, tmp_path, mock_keychain):
        """Test get_default_config_path prefers existing files."""
        # Create a config in one of the expected locations
        config_dir = tmp_path / ".config" / "rmirror"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.yaml"
        config_file.write_text("api:\n  url: http://test.com\n")

        with patch.object(Path, "home", return_value=tmp_path):
            path = Config.get_default_config_path()

        # Should find the file we created
        assert path.exists()

    def test_get_default_config_path_fallback(self, tmp_path, mock_keychain):
        """Test get_default_config_path returns default when no file exists."""
        # No config files exist
        with patch.object(Path, "home", return_value=tmp_path):
            path = Config.get_default_config_path()

        # Should return the default path (even if it doesn't exist)
        assert ".config/rmirror/config.yaml" in str(path) or ".rmirror/config.yaml" in str(path)


class TestConfigValidation:
    """Test configuration validation."""

    def test_nested_config_models(self, mock_keychain):
        """Test nested configuration models are created correctly."""
        config = Config()

        assert isinstance(config.api, APIConfig)
        assert isinstance(config.remarkable, ReMarkableConfig)
        assert isinstance(config.web, WebConfig)
        assert isinstance(config.tray, TrayConfig)
        assert isinstance(config.sync, SyncConfig)

    def test_config_from_dict(self, mock_keychain):
        """Test creating config from dictionary."""
        data = {
            "api": {
                "url": "http://custom.api/v1",
                "email": "custom@example.com",
            },
            "sync": {
                "batch_size": 20,
                "max_pages_per_notebook": 50,
            },
        }

        config = Config(**data)

        assert config.api.url == "http://custom.api/v1"
        assert config.api.email == "custom@example.com"
        assert config.sync.batch_size == 20
        assert config.sync.max_pages_per_notebook == 50


class TestSyncConfigEdgeCases:
    """Test sync configuration edge cases."""

    def test_max_pages_none_means_unlimited(self, mock_keychain):
        """Test max_pages_per_notebook=None means unlimited."""
        config = SyncConfig(max_pages_per_notebook=None)

        assert config.max_pages_per_notebook is None

    def test_max_pages_zero(self, mock_keychain):
        """Test max_pages_per_notebook=0 is valid (sync none)."""
        config = SyncConfig(max_pages_per_notebook=0)

        assert config.max_pages_per_notebook == 0

    def test_selected_notebooks_with_sync_all(self, mock_keychain):
        """Test selected_notebooks is ignored when sync_all_notebooks=True."""
        config = SyncConfig(
            sync_all_notebooks=True,
            selected_notebooks=["uuid-1", "uuid-2"],
        )

        # Both values are stored, but sync_all_notebooks takes precedence at runtime
        assert config.sync_all_notebooks is True
        assert config.selected_notebooks == ["uuid-1", "uuid-2"]

    def test_batch_size_boundaries(self, mock_keychain):
        """Test batch_size with various values."""
        # Small batch
        config = SyncConfig(batch_size=1)
        assert config.batch_size == 1

        # Large batch
        config = SyncConfig(batch_size=100)
        assert config.batch_size == 100
