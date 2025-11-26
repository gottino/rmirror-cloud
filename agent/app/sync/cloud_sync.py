"""
Cloud sync client for uploading reMarkable files to rMirror Cloud backend.
"""

import asyncio
import logging
from pathlib import Path
from typing import Optional

import httpx

from app.config import Config

logger = logging.getLogger(__name__)


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
        # Create HTTP client if not exists
        if self.client is None:
            self.client = httpx.AsyncClient(timeout=300.0)  # 5 minute timeout for OCR
            logger.debug(f"Created HTTP client with 300s timeout")

        # If we already have a token (from any source), verify it's valid
        if self.config.api.token:
            try:
                # Test the token with a simple API call
                logger.debug(f"Verifying existing JWT token")
                response = await self.client.get(
                    f"{self.config.api.url}/sync/stats",
                    headers={"Authorization": f"Bearer {self.config.api.token}"}
                )
                response.raise_for_status()
                self.authenticated = True
                auth_method = "Clerk" if self.config.api.use_clerk_auth else "password"
                logger.info(f"✓ Authenticated with rMirror Cloud using existing token ({auth_method})")
                print(f"✓ Authenticated with rMirror Cloud using existing token ({auth_method})")
                return True
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 401:
                    logger.warning("JWT token expired or invalid")
                    # Token expired - if using Clerk, need to re-auth via web
                    if self.config.api.use_clerk_auth:
                        raise CloudSyncError(
                            "Authentication token expired. Please sign in again via the web interface."
                        )
                    # Otherwise, fall through to password auth below
                    logger.info("Token expired, will try password authentication")
                else:
                    raise CloudSyncError(f"Token verification failed: {e}")
            except Exception as e:
                # Log the actual exception for debugging
                logger.error(f"Token verification error: {type(e).__name__}: {e}", exc_info=True)
                # If using Clerk auth, we can't fall back to password auth
                if self.config.api.use_clerk_auth:
                    raise CloudSyncError(f"Token verification failed: {e}")
                # Otherwise fall through to password auth
                logger.info("Token verification failed, will try password authentication")

        # Fall back to password authentication if configured
        if not self.config.api.use_clerk_auth:
            if not self.config.api.email or not self.config.api.password:
                raise CloudSyncError("API credentials not configured")

            try:
                logger.debug(f"Authenticating with {self.config.api.url}/auth/login")
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

                logger.info(f"✓ Authenticated with rMirror Cloud as {self.config.api.email}")
                print(f"✓ Authenticated with rMirror Cloud as {self.config.api.email}")
                return True

            except httpx.HTTPStatusError as e:
                logger.error(f"Authentication failed with status {e.response.status_code}: {e}")
                if e.response.status_code == 401:
                    raise CloudSyncError("Invalid email or password")
                raise CloudSyncError(f"Authentication failed: {e}")
            except Exception as e:
                logger.error(f"Authentication error: {e}", exc_info=True)
                raise CloudSyncError(f"Authentication error: {e}")

        # If we got here with Clerk auth but no token, user needs to sign in
        raise CloudSyncError(
            "Please sign in via the web interface at http://localhost:5555"
        )

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
            logger.error(f"File not found: {file_path}")
            raise CloudSyncError(f"File not found: {file_path}")

        try:
            # For .rm files, use the /processing/rm-file endpoint
            if file_type == "rm":
                logger.info(f"📤 Starting upload of .rm file: {file_path.name}")

                # Look for corresponding .metadata file
                metadata_path = file_path.parent.parent / f"{notebook_uuid}.metadata"

                files_to_upload = {
                    "rm_file": (file_path.name, open(file_path, "rb"), "application/octet-stream")
                }

                # Add metadata file if it exists
                if metadata_path.exists():
                    logger.debug(f"Including metadata file: {metadata_path.name}")
                    files_to_upload["metadata_file"] = (
                        metadata_path.name,
                        open(metadata_path, "rb"),
                        "application/json"
                    )
                else:
                    logger.warning(f"Metadata file not found: {metadata_path}")

                try:
                    logger.debug(f"POST {self.config.api.url}/processing/rm-file (timeout=300s)")
                    logger.debug(f"Files: {list(files_to_upload.keys())}")

                    response = await self.client.post(
                        f"{self.config.api.url}/processing/rm-file",
                        files=files_to_upload,
                        headers=self._get_headers(),
                    )

                    logger.debug(f"Response status: {response.status_code}")
                    logger.debug(f"Response headers: {dict(response.headers)}")

                    response.raise_for_status()

                    response_data = response.json()
                    logger.debug(f"Response data: {response_data}")

                    # Log OCR'd text at INFO level for visibility
                    if response_data.get('extracted_text'):
                        logger.info(f"✓ OCR extracted text: {response_data['extracted_text'][:200]}{'...' if len(response_data['extracted_text']) > 200 else ''}")

                finally:
                    # Close all file handles
                    for file_tuple in files_to_upload.values():
                        file_tuple[1].close()

                logger.info(f"✓ Upload complete: {file_path.name}")
                print(f"✓ Uploaded: {file_path.name}")
                return response_data

            # For other file types (metadata, content), we currently skip them
            # as they'll be included with the .rm file upload
            else:
                logger.debug(f"Skipping {file_type} file (handled with .rm upload)")
                print(f"⏭️  Skipping {file_type} file (handled with .rm upload)")
                return {"success": True, "skipped": True}

        except httpx.HTTPStatusError as e:
            logger.error(
                f"HTTP error during upload of {file_path.name}: "
                f"status={e.response.status_code}, body={e.response.text}"
            )

            if e.response.status_code == 401:
                # Token expired, re-authenticate and retry
                logger.info("Token expired, re-authenticating...")
                self.authenticated = False
                await self.authenticate()
                return await self.upload_file(file_path, notebook_uuid, file_type)

            raise CloudSyncError(f"Upload failed for {file_path.name}: {e}")
        except httpx.TimeoutException as e:
            logger.error(f"Upload timeout for {file_path.name}: {e}")
            raise CloudSyncError(f"Upload timeout for {file_path.name}: Request took longer than 300 seconds")
        except Exception as e:
            logger.error(f"Upload error for {file_path.name}: {e}", exc_info=True)
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
