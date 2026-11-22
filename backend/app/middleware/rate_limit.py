"""Shared, user-aware rate limiting.

There is one ``Limiter`` for the whole app (``limiter`` below); every router
decorates its endpoints with it and ``app.main`` installs it.

Keys
    ``get_rate_limit_key`` returns ``user:<id>`` when an auth dependency has
    resolved the user for this request (``get_clerk_user`` and
    ``get_obsidian_user`` store the id on ``request.state``), and the client
    IP otherwise. It never decodes tokens itself.

Where limits are checked
    * Routes with an explicit ``@limiter.limit(...)`` are checked by the
      decorator when the endpoint is called, i.e. after FastAPI has run the
      route's dependencies. Authenticated routes are therefore keyed per user.
      Requests that fail authentication never reach the decorator.
    * Every other route gets ``settings.rate_limit_default`` from
      ``RateLimitMiddleware`` (slowapi's ASGI middleware with a fix for
      streamed responses). The middleware runs before authentication, so
      the default limit is always keyed by client IP.

Storage
    ``settings.rate_limit_storage_uri`` (default ``memory://``). Production
    has no Redis and ``limits`` has no PostgreSQL backend, so counters live in
    each uvicorn worker process: with 2 workers a client can make up to twice
    each configured limit. Swap the URI for a shared backend to tighten this.
"""

import logging

from fastapi import FastAPI, Request
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIASGIMiddleware, _ASGIMiddlewareResponder
from slowapi.util import get_remote_address
from starlette.types import Message, Receive, Scope, Send

from app.config import get_settings

logger = logging.getLogger(__name__)

# Attribute on ``request.state`` that the auth dependencies set to the
# authenticated user's id.
RATE_LIMIT_USER_ATTR = "rate_limit_user_id"


def set_rate_limit_user(request: Request, user_id: int) -> None:
    """Record the authenticated user so the limiter keys this request by user."""
    setattr(request.state, RATE_LIMIT_USER_ATTR, user_id)


def get_rate_limit_key(request: Request) -> str:
    """
    Rate limit key: ``user:<id>`` once auth has resolved the user, else the IP.

    Args:
        request: FastAPI request object

    Returns:
        Rate limit key string
    """
    user_id = getattr(request.state, RATE_LIMIT_USER_ATTR, None)
    if user_id is not None:
        return f"user:{user_id}"
    return get_remote_address(request)


_settings = get_settings()

# Limit strings, format "X/period". Values come from settings (see config.py).
DEFAULT_LIMIT = _settings.rate_limit_default
UNAUTHENTICATED_LIMIT = _settings.rate_limit_unauthenticated
WEBHOOK_LIMIT = _settings.rate_limit_webhook
OBSIDIAN_SYNC_LIMIT = _settings.rate_limit_obsidian_sync
UPLOAD_LIMIT = _settings.rate_limit_upload

# Auth endpoint limits (very strict - token minting)
AUTH_ENDPOINT_LIMIT = "10/minute"

# The single limiter shared by every router. key_style="endpoint" gives each
# endpoint function one bucket per key, instead of one per URL (which would
# give every distinct path parameter its own budget).
limiter = Limiter(
    key_func=get_rate_limit_key,
    default_limits=[DEFAULT_LIMIT],
    storage_uri=_settings.rate_limit_storage_uri,
    key_style="endpoint",
)


class _StartOnceResponder(_ASGIMiddlewareResponder):
    """slowapi's responder, sending ``http.response.start`` only once.

    slowapi 0.1.9 holds back the start message and re-sends it before every
    body message. A response sent in more than one body message (any
    ``StreamingResponse``) then fails on its second chunk, and the client
    receives only the first one: page PDFs arrived as 9 bytes.
    """

    _started = False

    async def send_wrapper(self, message: Message) -> None:
        if message["type"] == "http.response.body" and self._started:
            await self.send(message)
            return
        if message["type"] == "http.response.body":
            self._started = True
        await super().send_wrapper(message)


class RateLimitMiddleware(SlowAPIASGIMiddleware):
    """``SlowAPIASGIMiddleware`` that passes multi-chunk responses through intact."""

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        await _StartOnceResponder(self.app)(scope, receive, send)


def install_rate_limiting(app: FastAPI) -> None:
    """Attach the shared limiter, its 429 handler and the default-limit middleware."""
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(RateLimitMiddleware)
