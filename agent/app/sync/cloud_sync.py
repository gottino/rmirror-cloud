"""
Cloud sync client for uploading reMarkable files to rMirror Cloud backend.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx

from app.config import Config

logger = logging.getLogger(__name__)


class CloudSyncError(Exception):
    """Cloud sync error."""

    pass


class RateLimitError(Exception):
    """Rate limit exceeded error (429)."""

    def __init__(self, message: str, retry_after: Optional[int] = None):
        super().__init__(message)
        self.retry_after = retry_after or 10  # Default 10 seconds


class QuotaExceededError(Exception):
    """Quota exceeded error."""

    def __init__(self, message: str, quota_status: Optional[dict] = None):
        super().__init__(message)
        self.quota_status = quota_status


class CloudSync:
    """Client for syncing files to rMirror Cloud backend."""

    def __init__(self, config: Config):
        """Initialize cloud sync client."""
        self.config = config
        self.client: Optional[httpx.AsyncClient] = None
        self.authenticated = False
        self.user_email: Optional[str] = None
        self.user_id: Optional[int] = None

    @property
    def _verify_ssl(self) -> bool:
        """Get SSL verification setting based on dev mode.

        Returns True (verify SSL) by default for production builds.
        Returns False only if RMIRROR_DEV_MODE=true for development/corporate proxy testing.
        """
        return not self.config.dev.dev_mode

    async def authenticate(self) -> bool:
        """
        Authenticate with the backend API and store the access token.

        Returns:
            True if authentication successful, False otherwise.
        """
        # Create HTTP client if not exists
        if self.client is None:
            # SSL verification controlled by RMIRROR_DEV_MODE env var
            # Default: verify=True (secure). Set RMIRROR_DEV_MODE=true for corporate proxies
            self.client = httpx.AsyncClient(timeout=300.0, verify=self._verify_ssl)
            ssl_status = "enabled" if self._verify_ssl else "disabled (dev mode)"
            logger.debug(f"Created HTTP client with 300s timeout (SSL verification {ssl_status})")

        # If we already have a token (from any source), verify it's valid
        if self.config.api.token:
            try:
                # Test the token with a simple API call
                logger.debug("Verifying existing JWT token")
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
        """Ensure we have a valid authentication token and HTTP client."""
        # Always create a new HTTP client if it doesn't exist
        # This is necessary because Flask creates a new event loop for each request,
        # and httpx clients are bound to the event loop they were created in
        if not self.client:
            self.client = httpx.AsyncClient(timeout=300.0, verify=self._verify_ssl)
            ssl_status = "enabled" if self._verify_ssl else "disabled (dev mode)"
            logger.debug(f"Created new HTTP client for current event loop (SSL verification {ssl_status})")

        # Re-authenticate if needed
        if not self.authenticated or not self.config.api.token:
            await self.authenticate()

    def _get_headers(self) -> dict[str, str]:
        """Get HTTP headers with authentication token."""
        if not self.config.api.token:
            raise CloudSyncError("Not authenticated")

        return {"Authorization": f"Bearer {self.config.api.token}"}

    def _parse_metadata_file(self, file_path: Path) -> dict:
        """
        Parse a .metadata file and convert to backend format.

        Args:
            file_path: Path to the .metadata file

        Returns:
            Dictionary with metadata in backend format
        """
        with open(file_path) as f:
            metadata = json.load(f)

        # Extract notebook UUID from filename
        notebook_uuid = file_path.stem

        # Convert reMarkable timestamps (milliseconds) to ISO 8601
        def convert_timestamp(timestamp_ms: str) -> Optional[str]:
            """Convert millisecond timestamp to ISO 8601."""
            if not timestamp_ms:
                return None
            try:
                timestamp_sec = int(timestamp_ms) / 1000.0
                dt = datetime.fromtimestamp(timestamp_sec)
                return dt.isoformat()
            except (ValueError, TypeError) as e:
                logger.warning(f"Failed to convert timestamp {timestamp_ms}: {e}")
                return None

        # Map reMarkable document types to backend types
        doc_type_map = {
            "DocumentType": "notebook",
            "CollectionType": "folder",
        }

        # Build metadata request
        metadata_request = {
            "notebook_uuid": notebook_uuid,
            "visible_name": metadata.get("visibleName", "Untitled"),
            "document_type": doc_type_map.get(metadata.get("type"), "notebook"),
        }

        # Add optional fields
        parent = metadata.get("parent", "")
        if parent and parent != "":
            metadata_request["parent_uuid"] = parent

        if "lastModified" in metadata:
            metadata_request["last_modified"] = convert_timestamp(metadata["lastModified"])

        if "lastOpened" in metadata:
            metadata_request["last_opened"] = convert_timestamp(metadata["lastOpened"])

        if "lastOpenedPage" in metadata:
            metadata_request["last_opened_page"] = metadata["lastOpenedPage"]

        if "version" in metadata:
            metadata_request["version"] = metadata["version"]

        if "pinned" in metadata:
            metadata_request["pinned"] = metadata["pinned"]

        if "deleted" in metadata:
            metadata_request["deleted"] = metadata["deleted"]

        return metadata_request

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

            # For .content files, upload to the content endpoint
            elif file_type == "content":
                logger.info(f"📤 Starting upload of .content file: {file_path.name}")

                try:
                    with open(file_path, "rb") as f:
                        files_to_upload = {
                            "content_file": (file_path.name, f, "application/json")
                        }

                        logger.debug(f"POST {self.config.api.url}/notebooks/{notebook_uuid}/content")

                        response = await self.client.post(
                            f"{self.config.api.url}/notebooks/{notebook_uuid}/content",
                            files=files_to_upload,
                            headers=self._get_headers(),
                        )

                        logger.debug(f"Response status: {response.status_code}")
                        response.raise_for_status()

                        response_data = response.json()
                        logger.debug(f"Response data: {response_data}")

                        if response_data.get('success'):
                            pages_mapped = response_data.get('pages_mapped', 0)
                            logger.info(f"✓ Content file processed: {pages_mapped} pages mapped")
                            print(f"✓ Content file uploaded: {pages_mapped} pages mapped")

                        return response_data

                except httpx.HTTPStatusError as e:
                    # If 404, the notebook doesn't exist yet - this is OK, skip silently
                    if e.response.status_code == 404:
                        logger.debug("Notebook not found for .content file (will be created when pages are uploaded)")
                        return {"success": True, "skipped": True, "reason": "notebook_not_found"}
                    raise

            # For .metadata files, upload to the metadata update endpoint
            elif file_type == "metadata":
                logger.info(f"📤 Starting upload of .metadata file: {file_path.name}")

                try:
                    # Parse metadata file
                    metadata_request = self._parse_metadata_file(file_path)

                    logger.debug(f"POST {self.config.api.url}/processing/metadata/update")
                    logger.debug(f"Metadata: {metadata_request}")

                    response = await self.client.post(
                        f"{self.config.api.url}/processing/metadata/update",
                        json=metadata_request,
                        headers=self._get_headers(),
                    )

                    logger.debug(f"Response status: {response.status_code}")
                    response.raise_for_status()

                    response_data = response.json()
                    logger.debug(f"Response data: {response_data}")

                    logger.info(f"✓ Metadata update complete: {file_path.name}")
                    print(f"✓ Metadata updated: {metadata_request['visible_name']}")
                    return response_data

                except httpx.HTTPStatusError as e:
                    # If 404, the notebook doesn't exist yet - this is OK
                    if e.response.status_code == 404:
                        logger.debug("Notebook not found for .metadata file (will be created when pages are uploaded)")
                        print("⏭️  Notebook not found yet (will sync when created)")
                        return {"success": True, "skipped": True, "reason": "notebook_not_found"}
                    raise

            # For other file types (pagedata), we currently skip them
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

            if e.response.status_code == 402:
                # Quota exceeded
                try:
                    error_data = e.response.json()
                    quota_info = error_data.get('quota', {})

                    # Format user-friendly message
                    used = quota_info.get('used', '?')
                    limit = quota_info.get('limit', '?')
                    reset_at = quota_info.get('reset_at', 'unknown')

                    message = (
                        f"⚠️  Monthly quota exceeded ({used}/{limit} pages used).\n"
                        f"   Quota resets: {reset_at}\n"
                        f"   Your notebooks continue syncing, but OCR transcription\n"
                        f"   and integrations are paused until quota resets."
                    )

                    logger.warning(message)
                    print(message)

                    raise QuotaExceededError(message, quota_status=quota_info)
                except (ValueError, KeyError):
                    # Couldn't parse error response, use generic message
                    message = "Monthly quota exceeded. Quota will reset at the start of next month."
                    logger.warning(message)
                    print(f"⚠️  {message}")
                    raise QuotaExceededError(message)

            if e.response.status_code == 429:
                # Rate limit exceeded - raise specific error for retry handling
                retry_after = int(e.response.headers.get("Retry-After", 10))
                logger.warning(f"Rate limit exceeded. Retry-After: {retry_after}s")
                raise RateLimitError(
                    f"Rate limit exceeded for {file_path.name}",
                    retry_after=retry_after
                )

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

        # File patterns to sync - separated into pages and metadata
        # We'll upload pages first, then the .content file to map them
        page_patterns = {
            "*.rm": "rm",
            "*.pagedata": "pagedata",
        }

        metadata_patterns = {
            "*.metadata": "metadata",
            "*.content": "content",
        }

        # Collect page files
        page_files = []
        for pattern, file_type in page_patterns.items():
            for file_path in notebook_dir.glob(pattern):
                page_files.append((file_path, file_type))

        # Collect metadata files
        metadata_files = []
        for pattern, file_type in metadata_patterns.items():
            for file_path in notebook_dir.glob(pattern):
                metadata_files.append((file_path, file_type))

        # Upload page files first
        for file_path, file_type in page_files:
            try:
                await self.upload_file(file_path, notebook_uuid, file_type)
                stats["uploaded"] += 1
            except CloudSyncError as e:
                print(f"✗ Failed to upload {file_path.name}: {e}")
                stats["failed"] += 1

        # Then upload metadata files (.content must come after pages are uploaded)
        for file_path, file_type in metadata_files:
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

    async def get_quota_status(self) -> dict:
        """
        Get quota status from the backend.

        Returns:
            Quota status data with fields:
            - quota_type: str (e.g., "ocr")
            - used: int (pages used)
            - limit: int (pages allowed)
            - is_exhausted: bool
            - is_near_limit: bool
            - percentage_used: float
            - reset_at: str (ISO datetime)

        Raises:
            CloudSyncError: If request fails
        """
        await self.ensure_authenticated()

        try:
            response = await self.client.get(
                f"{self.config.api.url}/quota/status",
                headers=self._get_headers(),
            )
            response.raise_for_status()

            quota_data = response.json()
            logger.debug(f"Quota status: {quota_data}")
            return quota_data

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                # Token expired, re-authenticate and retry
                self.authenticated = False
                await self.authenticate()
                return await self.get_quota_status()

            logger.error(f"Quota status request failed: status={e.response.status_code}")
            raise CloudSyncError(f"Quota status request failed: {e}")
        except Exception as e:
            logger.error(f"Quota status request error: {e}")
            raise CloudSyncError(f"Quota status request error: {e}")

    async def get_user_info(self) -> dict:
        """
        Get current user info from the backend.

        Returns:
            User info with fields:
            - id: int
            - email: str
            - full_name: str (optional)

        Raises:
            CloudSyncError: If request fails
        """
        await self.ensure_authenticated()

        try:
            response = await self.client.get(
                f"{self.config.api.url}/users/me",
                headers=self._get_headers(),
            )
            response.raise_for_status()

            user_data = response.json()
            # Cache user info
            self.user_email = user_data.get('email')
            self.user_id = user_data.get('id')
            logger.debug(f"User info: {user_data}")
            return user_data

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                # Token expired
                self.authenticated = False
                raise CloudSyncError("Authentication expired. Please sign in again.")

            logger.error(f"User info request failed: status={e.response.status_code}")
            raise CloudSyncError(f"User info request failed: {e}")
        except Exception as e:
            logger.error(f"User info request error: {e}")
            raise CloudSyncError(f"User info request error: {e}")

    def logout(self) -> None:
        """
        Clear authentication state and stored token.

        Note: We keep use_clerk_auth unchanged so the sign-in modal
        shows the OAuth option, not password auth.
        """
        self.authenticated = False
        self.user_email = None
        self.user_id = None
        self.config.api.token = None
        # Keep use_clerk_auth unchanged - don't reset auth method preference
        self.config.save()
        logger.info("User logged out, token cleared")

    def format_quota_display(self, quota_data: dict) -> str:
        """
        Format quota data for display.

        Args:
            quota_data: Quota status from get_quota_status()

        Returns:
            Formatted string for display
        """
        used = quota_data.get('used', 0)
        limit = quota_data.get('limit', 30)
        percentage = quota_data.get('percentage_used', 0.0)
        reset_at = quota_data.get('reset_at', 'unknown')
        is_exhausted = quota_data.get('is_exhausted', False)
        is_near_limit = quota_data.get('is_near_limit', False)

        # Color-code based on usage (for terminal output)
        if is_exhausted:
            status_emoji = "🔴"
            status_text = "QUOTA EXCEEDED"
        elif is_near_limit:
            status_emoji = "🟡"
            status_text = "APPROACHING LIMIT"
        else:
            status_emoji = "🟢"
            status_text = "ACTIVE"

        # Format the display
        remaining = max(0, limit - used)
        return (
            f"{status_emoji} Quota Status: {status_text}\n"
            f"   Pages used: {used}/{limit} ({percentage:.0f}%)\n"
            f"   Pages remaining: {remaining}\n"
            f"   Resets: {reset_at}"
        )

    async def close(self) -> None:
        """Close the HTTP client."""
        if self.client:
            await self.client.aclose()
            self.client = None
