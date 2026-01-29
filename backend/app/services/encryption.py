"""Encryption service for sensitive data using Fernet (symmetric encryption).

Used for encrypting integration credentials at rest.
"""

import base64
import hashlib
import json
from typing import Any

from cryptography.fernet import Fernet

from app.config import get_settings


class EncryptionService:
    """
    Handles encryption and decryption of sensitive data.

    Uses Fernet (symmetric encryption) with a master key from environment.
    Each user gets a derived key based on master key + user_id salt.
    """

    def __init__(self):
        """Initialize encryption service with master key from environment."""
        settings = get_settings()
        master_key = settings.integration_master_key

        if not master_key:
            raise ValueError(
                "INTEGRATION_MASTER_KEY environment variable is required. "
                "Generate one with: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
            )

        try:
            # Validate the master key format
            self.master_fernet = Fernet(master_key.encode() if isinstance(master_key, str) else master_key)
        except Exception as e:
            raise ValueError(f"Invalid INTEGRATION_MASTER_KEY format: {e}")

    def _get_user_key(self, user_id: int) -> Fernet:
        """
        Derive a user-specific encryption key.

        Uses SHA256 to derive a deterministic key from master key + user_id.

        Args:
            user_id: User ID to derive key for

        Returns:
            Fernet instance with user-specific key
        """
        # Get master key bytes
        master_key_bytes = self.master_fernet._encryption_key  # Access the raw key

        # Create deterministic salt from user_id
        user_salt = f"user_{user_id}_salt".encode()

        # Derive user key using SHA256 hash of master key + user salt
        key_material = hashlib.sha256(master_key_bytes + user_salt).digest()

        # Encode as base64 for Fernet (Fernet expects url-safe base64-encoded 32 bytes)
        user_key = base64.urlsafe_b64encode(key_material)

        return Fernet(user_key)

    def encrypt_config(self, config_dict: dict[str, Any], user_id: int) -> str:
        """
        Encrypt a configuration dictionary for a specific user.

        Args:
            config_dict: Configuration data to encrypt (e.g., API keys, tokens)
            user_id: User ID for key derivation

        Returns:
            Encrypted configuration as base64 string

        Example:
            >>> config = {"notion_token": "secret_xyz", "database_id": "abc123"}
            >>> encrypted = service.encrypt_config(config, user_id=42)
        """
        user_fernet = self._get_user_key(user_id)

        # Serialize config to JSON
        config_json = json.dumps(config_dict)

        # Encrypt
        encrypted_bytes = user_fernet.encrypt(config_json.encode())

        # Return as string
        return encrypted_bytes.decode()

    def decrypt_config(self, encrypted_config: str, user_id: int) -> dict[str, Any]:
        """
        Decrypt a configuration string for a specific user.

        Args:
            encrypted_config: Encrypted configuration string (or legacy unencrypted JSON)
            user_id: User ID for key derivation

        Returns:
            Decrypted configuration dictionary

        Raises:
            cryptography.fernet.InvalidToken: If decryption fails (wrong key or corrupted data)
            json.JSONDecodeError: If content is neither valid encrypted data nor valid JSON

        Example:
            >>> encrypted = "gAAAAABh..."
            >>> config = service.decrypt_config(encrypted, user_id=42)
            >>> print(config["notion_token"])
        """
        # Handle legacy unencrypted JSON configs (migration path)
        # Fernet-encrypted data always starts with 'gAAAAA'
        if encrypted_config.startswith("{"):
            try:
                return json.loads(encrypted_config)
            except json.JSONDecodeError:
                pass  # Fall through to normal decryption

        user_fernet = self._get_user_key(user_id)

        # Decrypt
        decrypted_bytes = user_fernet.decrypt(encrypted_config.encode())

        # Parse JSON
        config_dict = json.loads(decrypted_bytes.decode())

        return config_dict

    @staticmethod
    def generate_master_key() -> str:
        """
        Generate a new master key for INTEGRATION_MASTER_KEY.

        Returns:
            Base64-encoded Fernet key as string

        Example:
            >>> key = EncryptionService.generate_master_key()
            >>> print(f"INTEGRATION_MASTER_KEY={key}")
        """
        return Fernet.generate_key().decode()


# Singleton instance
_encryption_service: EncryptionService | None = None


def get_encryption_service() -> EncryptionService:
    """
    Get or create the singleton encryption service instance.

    Returns:
        EncryptionService instance

    Example:
        >>> from app.services.encryption import get_encryption_service
        >>> service = get_encryption_service()
        >>> encrypted = service.encrypt_config({"key": "value"}, user_id=1)
    """
    global _encryption_service

    if _encryption_service is None:
        _encryption_service = EncryptionService()

    return _encryption_service
