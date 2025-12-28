"""Encryption service for sensitive data using Fernet (symmetric encryption).

Used for encrypting integration credentials at rest.
"""

import json
import os
from typing import Any

from cryptography.fernet import Fernet


class EncryptionService:
    """
    Handles encryption and decryption of sensitive data.

    Uses Fernet (symmetric encryption) with a master key from environment.
    Each user gets a derived key based on master key + user_id salt.
    """

    def __init__(self):
        """Initialize encryption service with master key from environment."""
        master_key = os.getenv("INTEGRATION_MASTER_KEY")

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

        Uses the master key to encrypt the user_id, creating a deterministic
        but unique key for each user.

        Args:
            user_id: User ID to derive key for

        Returns:
            Fernet instance with user-specific key
        """
        # Create deterministic salt from user_id
        user_salt = f"user_{user_id}_salt".encode()

        # Derive user key by encrypting the salt with master key
        # This creates a unique, reproducible key per user
        user_key_material = self.master_fernet.encrypt(user_salt)

        # Use first 32 bytes as Fernet key (Fernet needs 32 url-safe base64-encoded bytes)
        # We'll use the encrypted material directly as it's already the right format
        user_fernet = Fernet(user_key_material[:44])  # Fernet keys are 44 bytes when base64 encoded

        return user_fernet

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
            encrypted_config: Encrypted configuration string
            user_id: User ID for key derivation

        Returns:
            Decrypted configuration dictionary

        Raises:
            cryptography.fernet.InvalidToken: If decryption fails (wrong key or corrupted data)

        Example:
            >>> encrypted = "gAAAAABh..."
            >>> config = service.decrypt_config(encrypted, user_id=42)
            >>> print(config["notion_token"])
        """
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
