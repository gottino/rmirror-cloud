"""User-aware rate limiting middleware.

This module provides rate limiting that distinguishes between:
- Authenticated users: Rate limited by user ID (generous limits)
- Unauthenticated requests: Rate limited by IP address (stricter limits)

This allows logged-in users to use the dashboard normally while
still protecting against abuse from unauthenticated sources.
"""

import logging

from fastapi import Request
from slowapi.util import get_remote_address

from app.auth.jwt import decode_access_token

logger = logging.getLogger(__name__)


def get_rate_limit_key(request: Request) -> str:
    """
    Get rate limit key based on authentication status.

    For authenticated requests: uses "user:{user_id}" as key
    For unauthenticated requests: uses IP address as key

    This allows authenticated users to have per-user rate limits
    while unauthenticated requests are limited by IP.

    Args:
        request: FastAPI request object

    Returns:
        Rate limit key string
    """
    # Try to extract user ID from Authorization header
    auth_header = request.headers.get("Authorization", "")

    if auth_header.startswith("Bearer "):
        token = auth_header[7:]  # Remove "Bearer " prefix
        try:
            payload = decode_access_token(token)
            if payload and "sub" in payload:
                user_id = payload["sub"]
                return f"user:{user_id}"
        except Exception:
            # Token invalid or expired - fall through to IP-based limiting
            pass

    # Fall back to IP-based limiting for unauthenticated requests
    return get_remote_address(request)


# Rate limit strings for different contexts
# Format: "X per Y" where Y is minute, hour, day, etc.

# Authenticated user limits (generous - per user)
AUTHENTICATED_LIMIT = "300/minute"  # 5 requests per second average

# Unauthenticated limits (strict - per IP)
UNAUTHENTICATED_LIMIT = "30/minute"  # 0.5 requests per second average

# Auth endpoint limits (very strict - prevent brute force)
AUTH_ENDPOINT_LIMIT = "10/minute"


def get_dynamic_limit(request: Request) -> str:
    """
    Get the appropriate rate limit based on authentication status.

    Args:
        request: FastAPI request object

    Returns:
        Rate limit string (e.g., "300/minute")
    """
    auth_header = request.headers.get("Authorization", "")

    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        try:
            payload = decode_access_token(token)
            if payload and "sub" in payload:
                return AUTHENTICATED_LIMIT
        except Exception:
            pass

    return UNAUTHENTICATED_LIMIT
