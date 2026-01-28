"""
Update checker for rMirror Agent.

Checks for new versions by fetching version.json from the CDN.
"""

import logging
from dataclasses import dataclass
from typing import Optional

import httpx
from packaging import version

from app.__version__ import __version__
from app.config import Config

logger = logging.getLogger(__name__)

VERSION_URL = "https://f000.backblazeb2.com/file/rmirror-downloads/releases/latest/version.json"


@dataclass
class UpdateInfo:
    """Information about available updates."""

    has_update: bool
    current_version: str
    latest_version: str
    download_url: Optional[str] = None
    release_notes: Optional[str] = None
    error: Optional[str] = None


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

        return UpdateInfo(
            has_update=has_update,
            current_version=current,
            latest_version=latest,
            download_url=data.get("download_url") if has_update else None,
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
