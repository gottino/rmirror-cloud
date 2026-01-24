"""Local filesystem storage implementation."""

from pathlib import Path
from typing import BinaryIO

import aiofiles

from app.storage.base import StorageService


class LocalStorageService(StorageService):
    """Local filesystem storage implementation."""

    def __init__(self, base_path: str = "./storage"):
        """
        Initialize local storage.

        Args:
            base_path: Base directory for file storage
        """
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _get_full_path(self, key: str) -> Path:
        """Get full filesystem path for a storage key."""
        # Ensure key doesn't escape base_path
        safe_key = key.lstrip("/").replace("..", "")
        return self.base_path / safe_key

    async def upload_file(
        self, file: BinaryIO, key: str, content_type: str | None = None
    ) -> str:
        """Upload file to local storage."""
        file_path = self._get_full_path(key)
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # Read file content
        content = file.read()

        # Write async
        async with aiofiles.open(file_path, "wb") as f:
            await f.write(content)

        return key

    async def download_file(self, key: str) -> bytes:
        """Download file from local storage."""
        file_path = self._get_full_path(key)

        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {key}")

        async with aiofiles.open(file_path, "rb") as f:
            return await f.read()

    async def delete_file(self, key: str) -> bool:
        """Delete file from local storage."""
        file_path = self._get_full_path(key)

        if file_path.exists():
            file_path.unlink()
            return True

        return False

    async def file_exists(self, key: str) -> bool:
        """Check if file exists in local storage."""
        return self._get_full_path(key).exists()

    async def get_file_url(self, key: str) -> str:
        """Get local file path as URL."""
        # For local storage, just return the relative path
        # In production with a web server, this would be a proper URL
        return f"/files/{key}"
