"""Abstract storage service interface."""

from abc import ABC, abstractmethod
from typing import BinaryIO


class StorageService(ABC):
    """Abstract interface for file storage services."""

    @abstractmethod
    async def upload_file(
        self, file: BinaryIO, key: str, content_type: str | None = None
    ) -> str:
        """
        Upload a file to storage.

        Args:
            file: File object to upload
            key: Storage key/path for the file
            content_type: MIME type of the file

        Returns:
            Storage key where file was saved
        """
        pass

    @abstractmethod
    async def download_file(self, key: str) -> bytes:
        """
        Download a file from storage.

        Args:
            key: Storage key of the file

        Returns:
            File contents as bytes
        """
        pass

    @abstractmethod
    async def delete_file(self, key: str) -> bool:
        """
        Delete a file from storage.

        Args:
            key: Storage key of the file

        Returns:
            True if deleted successfully
        """
        pass

    @abstractmethod
    async def file_exists(self, key: str) -> bool:
        """
        Check if a file exists in storage.

        Args:
            key: Storage key to check

        Returns:
            True if file exists
        """
        pass

    @abstractmethod
    async def get_file_url(self, key: str) -> str:
        """
        Get a URL to access the file.

        Args:
            key: Storage key of the file

        Returns:
            URL to access the file
        """
        pass
