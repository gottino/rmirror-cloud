"""
Update checker for rMirror Agent.

Checks for new versions by fetching version.json from the CDN.
"""

import logging
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlsplit

import httpx
from packaging import version

from app.__version__ import __version__
from app.config import Config

logger = logging.getLogger(__name__)

VERSION_URL = "https://f000.backblazeb2.com/file/rmirror-downloads/releases/latest/version.json"

# Download URLs are only accepted under the same bucket prefix that
# VERSION_URL lives in (everything before the "releases/..." path).
_ALLOWED_DOWNLOAD_PREFIX = VERSION_URL.rsplit("/releases/", 1)[0] + "/"


def is_allowed_download_url(url: object) -> bool:
    """Return True if url is https and lies under the release bucket prefix."""
    if not isinstance(url, str):
        return False
    try:
        parts = urlsplit(url)
        allowed = urlsplit(_ALLOWED_DOWNLOAD_PREFIX)
        port = parts.port
    except ValueError:
        return False
    if parts.scheme != "https" or parts.username or parts.password:
        return False
    if port not in (None, 443):
        return False
    if (parts.hostname or "").lower() != allowed.hostname:
        return False
    # Reject path tricks such as "/file/bucket/../other"
    segments = parts.path.split("/")
    if ".." in segments or "." in segments or "%" in parts.path:
        return False
    return parts.path.startswith(allowed.path)


@dataclass
class UpdateInfo:
    """Information about available updates."""

    has_update: bool
    current_version: str
    latest_version: str
    download_url: Optional[str] = None
    release_notes: Optional[str] = None
    error: Optional[str] = None


def _safe_url_for_log(url: object) -> str:
    """Scheme, host and path only: no query string, fragment or credentials."""
    if not isinstance(url, str):
        return "<not a string>"
    try:
        parts = urlsplit(url)
        return f"{parts.scheme}://{parts.hostname or ''}{parts.path}"
    except ValueError:
        return "<unparseable>"


async def check_for_updates() -> UpdateInfo:
    """
    Check if a newer version of the agent is available.

    Returns:
        UpdateInfo with update details or error information.
    """
    current = __version__

    try:
        # Respect dev_mode for SSL verification (corporate proxies)
        config = Config.load()
        verify_ssl = not config.dev.dev_mode

        async with httpx.AsyncClient(timeout=10.0, verify=verify_ssl) as client:
            response = await client.get(VERSION_URL)
            response.raise_for_status()
            data = response.json()

        latest = data.get("version", current)

        try:
            has_update = version.parse(latest) > version.parse(current)
        except version.InvalidVersion:
            # If version parsing fails, do simple string comparison
            has_update = latest != current

        download_url = data.get("download_url") if has_update else None
        if has_update and not is_allowed_download_url(download_url):
            # Never log the URL's query string (it may carry tokens)
            logger.warning(
                "Ignoring update: download_url is not under the release bucket (%s)",
                _safe_url_for_log(download_url),
            )
            return UpdateInfo(
                has_update=False,
                current_version=current,
                latest_version=current,
            )

        return UpdateInfo(
            has_update=has_update,
            current_version=current,
            latest_version=latest,
            download_url=download_url,
            release_notes=data.get("release_notes") if has_update else None,
        )

    except httpx.TimeoutException:
        logger.warning("Update check timed out")
        return UpdateInfo(
            has_update=False,
            current_version=current,
            latest_version=current,
            error="Connection timed out. Please check your internet connection.",
        )

    except httpx.HTTPStatusError as e:
        logger.warning(f"Update check failed with status {e.response.status_code}")
        return UpdateInfo(
            has_update=False,
            current_version=current,
            latest_version=current,
            error=f"Server returned error: {e.response.status_code}",
        )

    except Exception as e:
        logger.warning(f"Update check failed: {e}")
        return UpdateInfo(
            has_update=False,
            current_version=current,
            latest_version=current,
            error="Unable to check for updates. Please try again later.",
        )
