"""
Secure credential storage using macOS Keychain.
"""

import logging
from typing import Optional

import keyring
from keyring.errors import KeyringError

logger = logging.getLogger(__name__)

# Service name for keychain entries
SERVICE_NAME = "com.rmirror.agent"


class KeychainManager:
    """Manager for securely storing and retrieving credentials from macOS Keychain."""

    def __init__(self, service_name: str = SERVICE_NAME):
        """
        Initialize keychain manager.

        Args:
            service_name: Service identifier for keychain entries
        """
        self.service_name = service_name

    def store_token(self, token: str, user_identifier: str = "default") -> bool:
        """
        Store authentication token securely in keychain.

        Args:
            token: JWT authentication token
            user_identifier: Identifier for the user (email or user ID)

        Returns:
            True if stored successfully, False otherwise
        """
        try:
            keyring.set_password(self.service_name, user_identifier, token)
            logger.info(f"Token stored securely in keychain for user: {user_identifier}")
            return True
        except KeyringError as e:
            logger.error(f"Failed to store token in keychain: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error storing token: {e}")
            return False

    def get_token(self, user_identifier: str = "default") -> Optional[str]:
        """
        Retrieve authentication token from keychain.

        Args:
            user_identifier: Identifier for the user (email or user ID)

        Returns:
            Authentication token if found, None otherwise
        """
        try:
            token = keyring.get_password(self.service_name, user_identifier)
            if token:
                logger.debug(f"Token retrieved from keychain for user: {user_identifier}")
            else:
                logger.debug(f"No token found in keychain for user: {user_identifier}")
            return token
        except KeyringError as e:
            logger.error(f"Failed to retrieve token from keychain: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error retrieving token: {e}")
            return None

    def delete_token(self, user_identifier: str = "default") -> bool:
        """
        Delete authentication token from keychain.

        Args:
            user_identifier: Identifier for the user (email or user ID)

        Returns:
            True if deleted successfully, False otherwise
        """
        try:
            keyring.delete_password(self.service_name, user_identifier)
            logger.info(f"Token deleted from keychain for user: {user_identifier}")
            return True
        except KeyringError as e:
            logger.error(f"Failed to delete token from keychain: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error deleting token: {e}")
            return False

    def has_token(self, user_identifier: str = "default") -> bool:
        """
        Check if a token exists in keychain.

        Args:
            user_identifier: Identifier for the user (email or user ID)

        Returns:
            True if token exists, False otherwise
        """
        return self.get_token(user_identifier) is not None


# Global instance
_keychain_manager: Optional[KeychainManager] = None


def get_keychain_manager() -> KeychainManager:
    """Get or create global KeychainManager instance."""
    global _keychain_manager
    if _keychain_manager is None:
        _keychain_manager = KeychainManager()
    return _keychain_manager
