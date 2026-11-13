"""Tests for per-purpose signing keys (app/auth/signing.py) and their users.

Invite tokens, Notion OAuth state and Todoist OAuth state are each signed
with a key derived from SECRET_KEY for that purpose, so a value signed for one
purpose is not accepted for another. Invite tokens signed with the raw
SECRET_KEY before this change are still accepted (transition period).
"""

import base64
import hashlib
import hmac
import json
import time

import pytest

from app.api import notion_oauth, todoist, waitlist
from app.auth import signing
from app.config import get_settings


def _legacy_sign(payload: dict) -> str:
    """Sign exactly as the code did before key separation (raw SECRET_KEY)."""
    payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()
    sig = hmac.new(
        get_settings().secret_key.encode(), payload_b64.encode(), hashlib.sha256
    ).hexdigest()
    return f"{payload_b64}.{sig}"


# ---------------------------------------------------------------------------
# derive_key / sign / verify
# ---------------------------------------------------------------------------


def test_derive_key_is_hmac_of_secret_with_label():
    expected = hmac.new(
        get_settings().secret_key.encode(), b"rmirror:invite-token", hashlib.sha256
    ).digest()
    assert signing.derive_key("invite-token") == expected


def test_derived_keys_differ_per_purpose_and_from_secret():
    keys = {
        signing.derive_key(p)
        for p in (
            signing.INVITE_TOKEN_PURPOSE,
            signing.NOTION_OAUTH_STATE_PURPOSE,
            signing.TODOIST_OAUTH_STATE_PURPOSE,
        )
    }
    assert len(keys) == 3
    assert get_settings().secret_key.encode() not in keys


def test_sign_and_verify_roundtrip():
    key = signing.derive_key("test")
    token = signing.sign({"a": 1, "exp": int(time.time()) + 60}, key)
    assert signing.verify(token, [key])["a"] == 1


def test_verify_rejects_wrong_key_expired_and_garbage():
    key = signing.derive_key("test")
    other = signing.derive_key("other")
    good = signing.sign({"exp": int(time.time()) + 60}, key)
    assert signing.verify(good, [other]) is None

    expired = signing.sign({"exp": int(time.time()) - 1}, key)
    assert signing.verify(expired, [key]) is None

    no_exp = signing.sign({"a": 1}, key)
    assert signing.verify(no_exp, [key]) is None

    for junk in ["", "abc", "a.b.c", "!!!.deadbeef", good + "x"]:
        assert signing.verify(junk, [key]) is None


def test_verify_rejects_non_object_payload():
    key = signing.derive_key("test")
    payload_b64 = base64.urlsafe_b64encode(b"[1, 2]").decode()
    sig = hmac.new(key, payload_b64.encode(), hashlib.sha256).hexdigest()
    assert signing.verify(f"{payload_b64}.{sig}", [key]) is None


# ---------------------------------------------------------------------------
# Invite tokens
# ---------------------------------------------------------------------------


def test_invite_token_roundtrip():
    token = waitlist._create_invite_token("a@example.com", 7)
    payload = waitlist._validate_invite_token(token)
    assert payload["email"] == "a@example.com"
    assert payload["wid"] == 7


def test_invite_token_is_signed_with_derived_key_not_raw_secret():
    token = waitlist._create_invite_token("a@example.com", 7)
    payload_b64, sig = token.split(".")
    raw = hmac.new(
        get_settings().secret_key.encode(), payload_b64.encode(), hashlib.sha256
    ).hexdigest()
    assert sig != raw


def test_legacy_invite_token_signed_with_raw_secret_still_valid():
    token = _legacy_sign({"email": "old@example.com", "wid": 3, "exp": int(time.time()) + 3600})
    payload = waitlist._validate_invite_token(token)
    assert payload is not None
    assert payload["email"] == "old@example.com"


def test_expired_legacy_invite_token_rejected():
    token = _legacy_sign({"email": "old@example.com", "wid": 3, "exp": int(time.time()) - 1})
    assert waitlist._validate_invite_token(token) is None


def test_oauth_state_is_not_a_valid_invite_token():
    state = notion_oauth._create_oauth_state(5)
    assert waitlist._validate_invite_token(state) is None
    state = todoist._create_oauth_state(5)
    assert waitlist._validate_invite_token(state) is None


# ---------------------------------------------------------------------------
# OAuth state
# ---------------------------------------------------------------------------


def test_notion_oauth_state_roundtrip():
    state = notion_oauth._create_oauth_state(5)
    assert notion_oauth._validate_oauth_state(state, 5) is True
    assert notion_oauth._validate_oauth_state(state, 6) is False


def test_todoist_oauth_state_roundtrip():
    state = todoist._create_oauth_state(5)
    assert todoist._validate_oauth_state(state) == 5


def _invite_key_signed(payload: dict) -> str:
    return signing.sign(payload, signing.derive_key(signing.INVITE_TOKEN_PURPOSE))


def test_oauth_state_signed_with_invite_key_is_rejected():
    payload = {"uid": 5, "exp": int(time.time()) + 600}
    forged = _invite_key_signed(payload)
    assert notion_oauth._validate_oauth_state(forged, 5) is False
    assert todoist._validate_oauth_state(forged) is None


def test_notion_and_todoist_states_are_not_interchangeable():
    assert todoist._validate_oauth_state(notion_oauth._create_oauth_state(5)) is None
    assert notion_oauth._validate_oauth_state(todoist._create_oauth_state(5), 5) is False


@pytest.mark.parametrize("module", ["notion", "todoist"])
def test_oauth_state_signed_with_raw_secret_is_rejected(module):
    """No legacy fallback for OAuth state: it only lives 10 minutes."""
    state = _legacy_sign({"uid": 5, "exp": int(time.time()) + 600})
    if module == "notion":
        assert notion_oauth._validate_oauth_state(state, 5) is False
    else:
        assert todoist._validate_oauth_state(state) is None
