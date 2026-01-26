"""
Pytest fixtures for agent tests.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.config import APIConfig, Config, ReMarkableConfig, SyncConfig, TrayConfig, WebConfig


@pytest.fixture
def mock_keychain():
    """Mock keychain manager to avoid system keychain access during tests."""
    mock_keychain_manager = MagicMock()
    mock_keychain_manager.get_token.return_value = None
    mock_keychain_manager.store_token.return_value = True
    mock_keychain_manager.delete_token.return_value = True

    with patch("app.config.get_keychain_manager", return_value=mock_keychain_manager):
        with patch("app.auth.keychain.get_keychain_manager", return_value=mock_keychain_manager):
            yield mock_keychain_manager


@pytest.fixture
def test_config(mock_keychain) -> Config:
    """Create a test configuration with sensible defaults."""
    config = Config(
        api=APIConfig(
            url="http://test-api.rmirror.io/api/v1",
            email="test@example.com",
            password="testpassword",
            use_clerk_auth=False,
        ),
        remarkable=ReMarkableConfig(
            source_directory="/tmp/remarkable-test",
            watch_enabled=False,
        ),
        web=WebConfig(
            enabled=False,
            port=5556,
        ),
        tray=TrayConfig(
            enabled=False,
        ),
        sync=SyncConfig(
            auto_sync=False,
            batch_size=5,
            retry_attempts=2,
        ),
    )
    return config


@pytest.fixture
def test_config_with_token(test_config, mock_keychain) -> Config:
    """Create a test configuration with a pre-set token."""
    mock_keychain.get_token.return_value = "test-jwt-token"
    test_config.api._token = "test-jwt-token"
    return test_config


@pytest.fixture
def temp_remarkable_dir(tmp_path: Path) -> Path:
    """Create a temporary reMarkable sync directory structure."""
    # Create directory structure
    remarkable_dir = tmp_path / "remarkable"
    remarkable_dir.mkdir()

    # Create a sample notebook directory
    notebook_uuid = "test-notebook-uuid-1234"
    notebook_dir = remarkable_dir / notebook_uuid
    notebook_dir.mkdir()

    # Create sample .metadata file
    metadata = {
        "visibleName": "Test Notebook",
        "type": "DocumentType",
        "parent": "",
        "lastModified": "1704067200000",  # 2024-01-01
        "version": 1,
        "pinned": False,
        "deleted": False,
    }
    import json
    with open(remarkable_dir / f"{notebook_uuid}.metadata", "w") as f:
        json.dump(metadata, f)

    # Create sample .content file
    content = {
        "pages": ["page-uuid-1", "page-uuid-2"],
    }
    with open(remarkable_dir / f"{notebook_uuid}.content", "w") as f:
        json.dump(content, f)

    # Create sample .rm files (empty binary files for testing)
    for page_uuid in content["pages"]:
        rm_file = notebook_dir / f"{page_uuid}.rm"
        rm_file.write_bytes(b"\x00" * 100)  # Dummy binary content

    return remarkable_dir


@pytest.fixture
def temp_config_file(tmp_path: Path) -> Path:
    """Create a temporary config file."""
    config_file = tmp_path / "config.yaml"
    config_content = """
api:
  url: http://localhost:8000/api/v1
  email: test@example.com
  use_clerk_auth: false
remarkable:
  source_directory: /tmp/remarkable-test
  watch_enabled: false
web:
  enabled: false
sync:
  auto_sync: false
"""
    config_file.write_text(config_content)
    return config_file
