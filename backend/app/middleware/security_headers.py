"""Security headers middleware for FastAPI.

Adds security headers to all responses to protect against common web vulnerabilities:
- HSTS: Force HTTPS connections
- X-Frame-Options: Prevent clickjacking
- X-Content-Type-Options: Prevent MIME sniffing
- X-XSS-Protection: Legacy XSS protection
- Referrer-Policy: Control referrer information
- Permissions-Policy: Restrict browser features
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.config import get_settings


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware to add security headers to all responses."""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        settings = get_settings()

        # Only add HSTS in production (when not in debug mode)
        # HSTS tells browsers to only use HTTPS for this domain
        if not settings.debug:
            # max-age=31536000 (1 year), includeSubDomains
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )

        # Prevent clickjacking - page cannot be embedded in iframes
        response.headers["X-Frame-Options"] = "DENY"

        # Prevent MIME type sniffing - browser must respect Content-Type
        response.headers["X-Content-Type-Options"] = "nosniff"

        # Legacy XSS protection (modern browsers use CSP instead)
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # Control referrer information sent with requests
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Restrict browser features (geolocation, camera, etc.)
        response.headers["Permissions-Policy"] = (
            "accelerometer=(), camera=(), geolocation=(), gyroscope=(), "
            "magnetometer=(), microphone=(), payment=(), usb=()"
        )

        # Content Security Policy - restrict resource loading
        # Note: API-only backend has relaxed CSP since it doesn't serve HTML
        # The dashboard (Next.js) should have its own stricter CSP
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "frame-ancestors 'none'; "
            "form-action 'self'"
        )

        return response
