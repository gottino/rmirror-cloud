"""
Cloud sync client for uploading reMarkable files to rMirror Cloud backend.
"""

import asyncio
from pathlib import Path
from typing import Optional

import httpx

from app.config import Config


class CloudSyncError(Exception):
    """Cloud sync error."""

    pass


class CloudSync:
    """Client for syncing files to rMirror Cloud backend."""

    def __init__(self, config: Config):
        """Initialize cloud sync client."""
        self.config = config
        self.client: Optional[httpx.AsyncClient] = None
        self.authenticated = False

    async def authenticate(self) -> bool:
        """
        Authenticate with the backend API and store the access token.

        Returns:
            True if authentication successful, False otherwise.
        """
        if not self.config.api.email or not self.config.api.password:
            raise CloudSyncError("API credentials not configured")

        # Create HTTP client if not exists
        if self.client is None:
            self.client = httpx.AsyncClient(timeout=30.0)

        try:
            # Login to get access token
            response = await self.client.post(
                f"{self.config.api.url}/auth/login",
                json={
                    "email": self.config.api.email,
                    "password": self.config.api.password,
                },
            )
            response.raise_for_status()

            data = response.json()
            self.config.api.token = data["access_token"]
            self.authenticated = True

            print(f"✓ Authenticated with rMirror Cloud as {self.config.api.email}")
            return True

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise CloudSyncError("Invalid email or password")
            raise CloudSyncError(f"Authentication failed: {e}")
        except Exception as e:
            raise CloudSyncError(f"Authentication error: {e}")

    async def ensure_authenticated(self) -> None:
        """Ensure we have a valid authentication token."""
        if not self.authenticated or not self.config.api.token:
            await self.authenticate()

    def _get_headers(self) -> dict[str, str]:
        """Get HTTP headers with authentication token."""
        if not self.config.api.token:
            raise CloudSyncError("Not authenticated")

        return {"Authorization": f"Bearer {self.config.api.token}"}

    async def upload_file(
        self, file_path: Path, notebook_uuid: str, file_type: str
    ) -> dict:
        """
        Upload a single file to the backend.

        Args:
            file_path: Path to the file to upload
            notebook_uuid: UUID of the notebook this file belongs to
            file_type: Type of file (.rm, .metadata, .content, etc.)

        Returns:
            Response data from the API

        Raises:
            CloudSyncError: If upload fails
        """
        await self.ensure_authenticated()

        if not file_path.exists():
            raise CloudSyncError(f"File not found: {file_path}")

        try:
            # For .rm files, use the /processing/rm-file endpoint
            if file_type == "rm":
                # Look for corresponding .metadata file
                metadata_path = file_path.parent.parent / f"{notebook_uuid}.metadata"

                files_to_upload = {
                    "rm_file": (file_path.name, open(file_path, "rb"), "application/octet-stream")
                }

                # Add metadata file if it exists
                if metadata_path.exists():
                    files_to_upload["metadata_file"] = (
                        metadata_path.name,
                        open(metadata_path, "rb"),
                        "application/json"
                    )

                try:
                    response = await self.client.post(
                        f"{self.config.api.url}/processing/rm-file",
                        files=files_to_upload,
                        headers=self._get_headers(),
                    )
                    response.raise_for_status()
                finally:
                    # Close all file handles
                    for file_tuple in files_to_upload.values():
                        file_tuple[1].close()

                print(f"✓ Uploaded: {file_path.name}")
                return response.json()

            # For other file types (metadata, content), we currently skip them
            # as they'll be included with the .rm file upload
            else:
                print(f"⏭️  Skipping {file_type} file (handled with .rm upload)")
                return {"success": True, "skipped": True}

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                # Token expired, re-authenticate and retry
                self.authenticated = False
                await self.authenticate()
                return await self.upload_file(file_path, notebook_uuid, file_type)

            raise CloudSyncError(f"Upload failed for {file_path.name}: {e}")
        except Exception as e:
            raise CloudSyncError(f"Upload error for {file_path.name}: {e}")

    async def sync_notebook(self, notebook_uuid: str, notebook_dir: Path) -> dict:
        """
        Sync all files for a notebook.

        Args:
            notebook_uuid: UUID of the notebook
            notebook_dir: Directory containing the notebook files

        Returns:
            Sync statistics

        Raises:
            CloudSyncError: If sync fails
        """
        await self.ensure_authenticated()

        if not notebook_dir.exists():
            raise CloudSyncError(f"Notebook directory not found: {notebook_dir}")

        stats = {
            "uploaded": 0,
            "failed": 0,
            "skipped": 0,
        }

        # File patterns to sync
        patterns = {
            "*.content": "content",
            "*.metadata": "metadata",
            "*.rm": "rm",
            "*.pagedata": "pagedata",
        }

        files_to_upload = []
        for pattern, file_type in patterns.items():
            for file_path in notebook_dir.glob(pattern):
                files_to_upload.append((file_path, file_type))

        # Upload files
        for file_path, file_type in files_to_upload:
            try:
                await self.upload_file(file_path, notebook_uuid, file_type)
                stats["uploaded"] += 1
            except CloudSyncError as e:
                print(f"✗ Failed to upload {file_path.name}: {e}")
                stats["failed"] += 1

        return stats

    async def trigger_ocr(self, notebook_uuid: str) -> dict:
        """
        Trigger OCR processing for a notebook.

        Args:
            notebook_uuid: UUID of the notebook

        Returns:
            Response data from the API

        Raises:
            CloudSyncError: If OCR trigger fails
        """
        await self.ensure_authenticated()

        try:
            response = await self.client.post(
                f"{self.config.api.url}/notebooks/uuid/{notebook_uuid}/ocr",
                headers=self._get_headers(),
            )
            response.raise_for_status()

            print(f"✓ Triggered OCR for notebook {notebook_uuid}")
            return response.json()

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                # Token expired, re-authenticate and retry
                self.authenticated = False
                await self.authenticate()
                return await self.trigger_ocr(notebook_uuid)

            raise CloudSyncError(f"OCR trigger failed: {e}")
        except Exception as e:
            raise CloudSyncError(f"OCR trigger error: {e}")

    async def get_sync_status(self) -> dict:
        """
        Get sync status from the backend.

        Returns:
            Sync status data

        Raises:
            CloudSyncError: If request fails
        """
        await self.ensure_authenticated()

        try:
            response = await self.client.get(
                f"{self.config.api.url}/sync/stats",
                headers=self._get_headers(),
            )
            response.raise_for_status()

            return response.json()

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                # Token expired, re-authenticate and retry
                self.authenticated = False
                await self.authenticate()
                return await self.get_sync_status()

            raise CloudSyncError(f"Status request failed: {e}")
        except Exception as e:
            raise CloudSyncError(f"Status request error: {e}")

    async def close(self) -> None:
        """Close the HTTP client."""
        if self.client:
            await self.client.aclose()
            self.client = None
