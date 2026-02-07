"""Unit tests for auth/jwt.py and auth/password.py.

Tests JWT token creation/decoding and password hashing/verification.
"""

import time
from datetime import timedelta
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
        from jose import jwt as jose_jwt

        token = jose_jwt.encode(
            {"sub": "user123", "exp": time.time() + 3600},
            "wrong-secret",
            algorithm="HS256",
        )
        assert self.decode_access_token(token) is None

    def test_decode_access_token_empty_string(self):
        """Empty string should return None."""
        assert self.decode_access_token("") is None


# ---------- Password Tests ----------

class TestPassword:
    """Tests for password hashing and verification."""

    def test_get_password_hash_returns_bcrypt_format(self):
        """Hash should be in bcrypt format ($2b$...)."""
        from app.auth.password import get_password_hash

        hashed = get_password_hash("mysecretpassword")
        assert hashed.startswith("$2b$")
        assert len(hashed) == 60  # bcrypt hashes are always 60 chars

    def test_verify_password_correct(self):
        """Correct password should verify successfully."""
        from app.auth.password import get_password_hash, verify_password

        hashed = get_password_hash("correctpassword")
        assert verify_password("correctpassword", hashed) is True

    def test_verify_password_wrong(self):
        """Wrong password should fail verification."""
        from app.auth.password import get_password_hash, verify_password

        hashed = get_password_hash("correctpassword")
        assert verify_password("wrongpassword", hashed) is False

    def test_hash_is_salted(self):
        """Two hashes of same password should differ (random salt)."""
        from app.auth.password import get_password_hash

        hash1 = get_password_hash("samepassword")
        hash2 = get_password_hash("samepassword")
        assert hash1 != hash2

    def test_unicode_password_round_trip(self):
        """Unicode passwords should hash and verify correctly."""
        from app.auth.password import get_password_hash, verify_password

        password = "p\u00e4ssw\u00f6rd\U0001f511"  # pässwörd🔑
        hashed = get_password_hash(password)
        assert verify_password(password, hashed) is True
        assert verify_password("plainascii", hashed) is False
