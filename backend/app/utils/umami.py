"""Fire-and-forget Umami analytics event tracking for backend events."""

import logging
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

# Shared async client for connection pooling
_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=5.0)
    return _client


async def track_event(
    name: str,
    data: dict[str, Any] | None = None,
    user_id: int | None = None,
) -> None:
    """
    Send an event to Umami's collect API. Fire-and-forget: never raises.

    Args:
        name: Event name (e.g. 'account_created')
        data: Optional event properties
        user_id: Optional user ID for session correlation (no PII)
    """
    settings = get_settings()
    if not settings.umami_url or not settings.umami_website_id:
        return

    payload: dict[str, Any] = {
        "type": "event",
        "payload": {
            "website": settings.umami_website_id,
            "url": "/api/backend",
            "name": name,
        },
    }

    if data:
        payload["payload"]["data"] = data

    if user_id is not None:
        payload["payload"].setdefault("data", {})["user_id"] = user_id

    try:
        client = _get_client()
        await client.post(
            f"{settings.umami_url.rstrip('/')}/api/send",
            json=payload,
            headers={"Content-Type": "application/json"},
        )
    except Exception:
        logger.debug("Failed to send Umami event %s", name, exc_info=True)
