"""Unit tests for auth/jwt.py (agent token creation/decoding)."""

import time
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

import pytest


# ---------- JWT Tests ----------

class TestJWT:
    """Tests for JWT token creation and validation."""

    @pytest.fixture(autouse=True)
    def _mock_settings(self):
        """Provide consistent settings for JWT tests."""
        mock_settings = MagicMock()
        mock_settings.secret_key = "test-secret-key-for-jwt-tests"
        mock_settings.algorithm = "HS256"
        mock_settings.access_token_expire_minutes = 60

        with patch("app.auth.jwt.settings", mock_settings):
            # Re-import to pick up mocked settings
            from app.auth.jwt import create_access_token, decode_access_token
            self.create_access_token = create_access_token
            self.decode_access_token = decode_access_token
            self._settings = mock_settings
            yield

    def test_create_access_token_returns_string(self):
        """create_access_token should return a JWT string."""
        token = self.create_access_token({"sub": "user123"})
        assert isinstance(token, str)
        assert len(token) > 0
        # JWT has three dot-separated parts
        assert token.count(".") == 2

    def test_create_access_token_with_custom_expiry(self):
        """create_access_token should accept custom expiration."""
        token = self.create_access_token(
            {"sub": "user123"},
            expires_delta=timedelta(minutes=5),
        )
        payload = self.decode_access_token(token)
        assert payload is not None
        assert payload["sub"] == "user123"

    def test_create_access_token_preserves_claims(self):
        """Custom claims should be preserved in the token payload."""
        token = self.create_access_token({
            "sub": "user123",
            "role": "admin",
            "org_id": 42,
        })
        payload = self.decode_access_token(token)
        assert payload["sub"] == "user123"
        assert payload["role"] == "admin"
        assert payload["org_id"] == 42

    def test_decode_access_token_round_trip(self):
        """Encoding then decoding should return the original data."""
        original = {"sub": "user456", "custom": "value"}
        token = self.create_access_token(original)
        payload = self.decode_access_token(token)
        assert payload is not None
        assert payload["sub"] == "user456"
        assert payload["custom"] == "value"
        assert "exp" in payload

    def test_decode_access_token_garbage_input(self):
        """Garbage input should return None."""
        assert self.decode_access_token("not.a.jwt") is None
        assert self.decode_access_token("garbage") is None

    def test_decode_access_token_expired_token(self):
        """Expired token should return None."""
        token = self.create_access_token(
            {"sub": "user123"},
            expires_delta=timedelta(seconds=-1),
        )
        assert self.decode_access_token(token) is None

    def test_decode_access_token_wrong_secret(self):
        """Token signed with different secret should return None."""
        import jwt as pyjwt

        token = pyjwt.encode(
            {"sub": "user123", "exp": time.time() + 3600},
            "wrong-secret",
            algorithm="HS256",
        )
        assert self.decode_access_token(token) is None

    def test_decode_access_token_empty_string(self):
        """Empty string should return None."""
        assert self.decode_access_token("") is None


# ---------- Token format compatibility ----------

# An agent token minted by the previous JWT library (python-jose) for fixed
# claims. Agents store their token for 30 days, so tokens minted before a
# library change must still decode, and new tokens must keep the same format.
LEGACY_AGENT_TOKEN = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJzdWIiOiI0MiIsInR5cGUiOiJhZ2VudCIsInZlciI6MywiZXhwIjo0MDcwOTA4ODAwfQ."
    "3D-hKnVKueUbJGV20Loby2ZZsY-FxCYxjwf4Befw7Vw"
)


class _FixedDatetime(datetime):
    """datetime whose utcnow() is 30 days before 2099-01-01 00:00 UTC."""

    @classmethod
    def utcnow(cls):
        return datetime(2098, 12, 2, 0, 0, 0)


class TestTokenFormatCompatibility:
    @pytest.fixture(autouse=True)
    def _mock_settings(self):
        mock_settings = MagicMock()
        mock_settings.secret_key = "test-secret-key-for-jwt-tests"
        mock_settings.algorithm = "HS256"
        mock_settings.access_token_expire_minutes = 60
        with patch("app.auth.jwt.settings", mock_settings):
            yield

    def test_new_agent_token_is_byte_identical_to_legacy_format(self):
        from app.auth.jwt import create_access_token

        with patch("app.auth.jwt.datetime", _FixedDatetime):
            token = create_access_token(
                {"sub": "42", "type": "agent", "ver": 3},
                expires_delta=timedelta(days=30),
            )
        assert token == LEGACY_AGENT_TOKEN

    def test_legacy_agent_token_still_decodes(self):
        from app.auth.jwt import decode_access_token

        payload = decode_access_token(LEGACY_AGENT_TOKEN)
        assert payload == {"sub": "42", "type": "agent", "ver": 3, "exp": 4070908800}

    def test_legacy_agent_token_accepted_by_request_auth_decoder(self):
        """clerk.get_current_user decodes HS256 agent tokens with PyJWT."""
        import jwt as pyjwt

        payload = pyjwt.decode(
            LEGACY_AGENT_TOKEN, "test-secret-key-for-jwt-tests", algorithms=["HS256"]
        )
        assert payload["type"] == "agent"
