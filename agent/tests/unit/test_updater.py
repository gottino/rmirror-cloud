"""Tests for the update checker's download URL validation."""

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app import updater
from app.updater import check_for_updates, is_allowed_download_url

PREFIX = updater.VERSION_URL.rsplit("/releases/", 1)[0]


@pytest.mark.parametrize(
    "url",
    [
        f"{PREFIX}/releases/v9.9.9/rMirror-9.9.9.dmg",
        f"{PREFIX}/releases/v9.9.9/rMirror-9.9.9-intel.dmg",
    ],
)
def test_allowed_urls(url):
    assert is_allowed_download_url(url)


@pytest.mark.parametrize(
    "url",
    [
        None,
        "",
        123,
        "http://f000.backblazeb2.com/file/rmirror-downloads/releases/x.dmg",
        "https://evil.example.com/file/rmirror-downloads/releases/x.dmg",
        "https://f000.backblazeb2.com.evil.example.com/file/rmirror-downloads/x.dmg",
        "https://f000.backblazeb2.com@evil.example.com/file/rmirror-downloads/x.dmg",
        "https://user:pw@f000.backblazeb2.com/file/rmirror-downloads/x.dmg",
        "https://f000.backblazeb2.com/file/other-bucket/releases/x.dmg",
        "https://f000.backblazeb2.com/file/rmirror-downloads-evil/x.dmg",
        "https://f000.backblazeb2.com/file/rmirror-downloads/../other/x.dmg",
        "https://f000.backblazeb2.com:8443/file/rmirror-downloads/x.dmg",
        "file:///etc/passwd",
        "javascript:alert(1)",
    ],
)
def test_rejected_urls(url):
    assert not is_allowed_download_url(url)


def _mock_client(payload):
    response = MagicMock()
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    client = MagicMock()
    client.get = AsyncMock(return_value=response)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


async def _check(payload):
    with patch("app.updater.httpx.AsyncClient", return_value=_mock_client(payload)), patch(
        "app.updater.Config"
    ):
        return await check_for_updates()


@pytest.mark.asyncio
async def test_update_with_allowed_url_is_offered():
    url = f"{PREFIX}/releases/v99.0.0/rMirror-99.0.0.dmg"
    info = await _check({"version": "99.0.0", "download_url": url, "release_notes": "n"})
    assert info.has_update
    assert info.download_url == url


@pytest.mark.asyncio
async def test_update_with_foreign_url_is_unavailable_and_query_not_logged(caplog):
    url = "https://evil.example.com/x.dmg?token=SECRETVALUE"
    with caplog.at_level(logging.WARNING, logger="app.updater"):
        info = await _check({"version": "99.0.0", "download_url": url})
    assert not info.has_update
    assert info.download_url is None
    assert "evil.example.com" in caplog.text
    assert "SECRETVALUE" not in caplog.text
    assert "token=" not in caplog.text
