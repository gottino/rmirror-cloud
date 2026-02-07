"""Unit tests for services/encryption.py.

Tests encryption/decryption round-trips, key derivation, and error handling.
"""

import pytest
from unittest.mock import patch, MagicMock

from cryptography.fernet import Fernet, InvalidToken


@pytest.fixture
def master_key():
    """Generate a valid Fernet key for testing."""
    return Fernet.generate_key().decode()


@pytest.fixture
def encryption_service(master_key):
    """Create an EncryptionService with a test master key."""
    mock_settings = MagicMock()
    mock_settings.integration_master_key = master_key

    with patch("app.services.encryption.get_settings", return_value=mock_settings):
        # Reset singleton so we get a fresh instance
        import app.services.encryption as enc_module
        enc_module._encryption_service = None

        from app.services.encryption import EncryptionService
        service = EncryptionService()
        yield service

        # Clean up singleton
        enc_module._encryption_service = None


class TestEncryptionService:
    """Tests for EncryptionService."""

    def test_encrypt_decrypt_round_trip(self, encryption_service):
        """Encrypt then decrypt should return the original config dict."""
        config = {"notion_token": "secret_xyz", "database_id": "abc123"}
        encrypted = encryption_service.encrypt_config(config, user_id=1)
        decrypted = encryption_service.decrypt_config(encrypted, user_id=1)
        assert decrypted == config

    def test_decrypt_with_wrong_user_id(self, encryption_service):
        """Decrypting with different user_id should raise InvalidToken."""
        config = {"key": "value"}
        encrypted = encryption_service.encrypt_config(config, user_id=1)
        with pytest.raises(InvalidToken):
            encryption_service.decrypt_config(encrypted, user_id=2)

    def test_different_users_produce_different_ciphertexts(self, encryption_service):
        """Same config encrypted for different users should differ."""
        config = {"token": "same_value"}
        encrypted_1 = encryption_service.encrypt_config(config, user_id=1)
        encrypted_2 = encryption_service.encrypt_config(config, user_id=2)
        assert encrypted_1 != encrypted_2

    def test_legacy_unencrypted_json_handled(self, encryption_service):
        """Legacy unencrypted JSON (starts with '{') should be returned as-is."""
        legacy_json = '{"notion_token": "old_token", "database_id": "old_db"}'
        result = encryption_service.decrypt_config(legacy_json, user_id=1)
        assert result == {"notion_token": "old_token", "database_id": "old_db"}

    def test_empty_dict_round_trip(self, encryption_service):
        """Empty dict should encrypt/decrypt correctly."""
        encrypted = encryption_service.encrypt_config({}, user_id=1)
        decrypted = encryption_service.decrypt_config(encrypted, user_id=1)
        assert decrypted == {}

    def test_nested_dict_with_special_chars(self, encryption_service):
        """Nested dict with special characters should round-trip correctly."""
        config = {
            "token": "secret_\u00fc\u00f6\u00e4",
            "nested": {"key": "value with spaces & symbols!"},
            "list": [1, 2, 3],
        }
        encrypted = encryption_service.encrypt_config(config, user_id=42)
        decrypted = encryption_service.decrypt_config(encrypted, user_id=42)
        assert decrypted == config

    def test_generate_master_key_returns_valid_fernet_key(self):
        """generate_master_key should return a valid Fernet key."""
        from app.services.encryption import EncryptionService

        key = EncryptionService.generate_master_key()
        assert isinstance(key, str)
        # Should not raise
        Fernet(key.encode())

    def test_missing_master_key_raises(self):
        """Missing INTEGRATION_MASTER_KEY should raise ValueError."""
        mock_settings = MagicMock()
        mock_settings.integration_master_key = None

        with patch("app.services.encryption.get_settings", return_value=mock_settings):
            import app.services.encryption as enc_module
            enc_module._encryption_service = None

            from app.services.encryption import EncryptionService
            with pytest.raises(ValueError, match="INTEGRATION_MASTER_KEY"):
                EncryptionService()

            enc_module._encryption_service = None
