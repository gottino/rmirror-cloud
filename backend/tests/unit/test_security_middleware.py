"""Unit tests for middleware/security_headers.py and middleware/rate_limit.py.

Tests security header injection and rate limit key extraction.
"""

import pytest
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.middleware.security_headers import SecurityHeadersMiddleware


# ---------- Security Headers Tests ----------

class TestSecurityHeaders:
    """Tests for SecurityHeadersMiddleware."""

    def _get_response(self, debug: bool):
        """Create a test app, make a request with mocked settings, return response."""
        mock_settings = MagicMock()
        mock_settings.debug = debug

        app = FastAPI()

        @app.get("/test")
        async def test_endpoint():
            return {"ok": True}

        app.add_middleware(SecurityHeadersMiddleware)

        # Patch must be active during the request (dispatch reads settings)
        with patch("app.middleware.security_headers.get_settings", return_value=mock_settings):
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

    def test_hsts_absent_in_debug(self):
        """HSTS header should be absent when debug=True."""
        response = self._get_response(debug=True)
        assert "Strict-Transport-Security" not in response.headers


# ---------- Rate Limit Tests ----------

class TestRateLimit:
    """Tests for rate limit key extraction and dynamic limits."""

    @pytest.fixture(autouse=True)
    def _mock_jwt_settings(self):
        """Mock settings used by the JWT module that rate_limit imports."""
        mock_settings = MagicMock()
        mock_settings.secret_key = "test-secret-for-rate-limit"
        mock_settings.algorithm = "HS256"
        mock_settings.access_token_expire_minutes = 60

        with patch("app.auth.jwt.settings", mock_settings):
            yield mock_settings

    def _make_request(self, auth_header: str | None = None) -> MagicMock:
        """Create a mock FastAPI Request."""
        request = MagicMock()
        headers = {}
        if auth_header:
            headers["Authorization"] = auth_header
        request.headers = headers
        request.client = MagicMock()
        request.client.host = "127.0.0.1"
        request.scope = {"type": "http"}
        return request

    def test_rate_limit_key_valid_bearer_token(self):
        """Valid Bearer token should return user:{id} key."""
        from app.auth.jwt import create_access_token
        from app.middleware.rate_limit import get_rate_limit_key

        token = create_access_token({"sub": "user42"})
        request = self._make_request(f"Bearer {token}")
        key = get_rate_limit_key(request)
        assert key == "user:user42"

    def test_rate_limit_key_missing_auth(self):
        """Missing auth should fall back to IP-based key."""
        from app.middleware.rate_limit import get_rate_limit_key

        request = self._make_request()
        with patch("app.middleware.rate_limit.get_remote_address", return_value="192.168.1.1"):
            key = get_rate_limit_key(request)
        assert key == "192.168.1.1"

    def test_rate_limit_key_invalid_token(self):
        """Invalid Bearer token should fall back to IP-based key."""
        from app.middleware.rate_limit import get_rate_limit_key

        request = self._make_request("Bearer invalid.token.here")
        with patch("app.middleware.rate_limit.get_remote_address", return_value="10.0.0.1"):
            key = get_rate_limit_key(request)
        assert key == "10.0.0.1"

    def test_dynamic_limit_authenticated(self):
        """Valid token should return authenticated limit."""
        from app.auth.jwt import create_access_token
        from app.middleware.rate_limit import get_dynamic_limit, AUTHENTICATED_LIMIT

        token = create_access_token({"sub": "user42"})
        request = self._make_request(f"Bearer {token}")
        assert get_dynamic_limit(request) == AUTHENTICATED_LIMIT

    def test_dynamic_limit_unauthenticated(self):
        """No token should return unauthenticated limit."""
        from app.middleware.rate_limit import get_dynamic_limit, UNAUTHENTICATED_LIMIT

        request = self._make_request()
        assert get_dynamic_limit(request) == UNAUTHENTICATED_LIMIT
