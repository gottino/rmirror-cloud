"""Unit tests for middleware/security_headers.py and middleware/rate_limit.py.

Tests security header injection and rate limit key extraction.
"""

from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.middleware.security_headers import SecurityHeadersMiddleware

# ---------- Security Headers Tests ----------

class TestSecurityHeaders:
    """Tests for SecurityHeadersMiddleware."""

    def _get_response(self, debug: bool = False):
        """Create a test app, make a request with DEBUG set as given, return response."""
        from app.config import get_settings

        settings = get_settings().model_copy(update={"debug": debug})

        app = FastAPI()

        @app.get("/test")
        async def test_endpoint():
            return {"ok": True}

        app.add_middleware(SecurityHeadersMiddleware)

        # create=True: the middleware no longer reads settings, but if it ever
        # does again, it must see these ones.
        with patch(
            "app.middleware.security_headers.get_settings",
            return_value=settings,
            create=True,
        ):
            client = TestClient(app)
            return client.get("/test")

    def test_x_frame_options_deny(self):
        """Response should include X-Frame-Options: DENY."""
        response = self._get_response(debug=False)
        assert response.headers["X-Frame-Options"] == "DENY"

    def test_x_content_type_options_nosniff(self):
        """Response should include X-Content-Type-Options: nosniff."""
        response = self._get_response(debug=False)
        assert response.headers["X-Content-Type-Options"] == "nosniff"

    def test_hsts_present_in_production(self):
        """HSTS header should be present when debug=False."""
        response = self._get_response(debug=False)
        assert "Strict-Transport-Security" in response.headers
        assert "max-age=31536000" in response.headers["Strict-Transport-Security"]

    def test_hsts_present_in_debug(self):
        """DEBUG only changes log verbosity: HSTS is still sent."""
        response = self._get_response(debug=True)
        assert "Strict-Transport-Security" in response.headers


# ---------- Rate Limit Tests ----------

class TestRateLimit:
    """Tests for rate limit key extraction.

    The key comes from ``request.state`` (set by the auth dependencies), never
    from decoding the Authorization header.
    """

    def _make_request(self, auth_header: str | None = None, user_id=None) -> MagicMock:
        """Create a mock FastAPI Request."""
        request = MagicMock()
        headers = {}
        if auth_header:
            headers["Authorization"] = auth_header
        request.headers = headers
        request.client = MagicMock()
        request.client.host = "127.0.0.1"
        request.scope = {"type": "http"}
        request.state = MagicMock(spec=[])  # no attributes set
        if user_id is not None:
            request.state.rate_limit_user_id = user_id
        return request

    def test_rate_limit_key_uses_user_recorded_by_auth(self):
        """A user recorded on request.state gives a user:{id} key."""
        from app.middleware.rate_limit import get_rate_limit_key

        request = self._make_request("Bearer whatever", user_id=42)
        assert get_rate_limit_key(request) == "user:42"

    def test_rate_limit_key_missing_auth(self):
        """Missing auth should fall back to IP-based key."""
        from app.middleware.rate_limit import get_rate_limit_key

        request = self._make_request()
        with patch("app.middleware.rate_limit.get_remote_address", return_value="192.168.1.1"):
            key = get_rate_limit_key(request)
        assert key == "192.168.1.1"

    def test_rate_limit_key_ignores_unverified_token(self):
        """A bearer token alone (auth not run or failed) does not pick the key."""
        from app.auth.jwt import create_access_token
        from app.middleware.rate_limit import get_rate_limit_key

        with patch("app.auth.jwt.settings") as mock_settings:
            mock_settings.secret_key = "test-secret-for-rate-limit"
            mock_settings.algorithm = "HS256"
            mock_settings.access_token_expire_minutes = 60
            token = create_access_token({"sub": "user42"})
        request = self._make_request(f"Bearer {token}")
        with patch("app.middleware.rate_limit.get_remote_address", return_value="10.0.0.1"):
            key = get_rate_limit_key(request)
        assert key == "10.0.0.1"
