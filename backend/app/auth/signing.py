"""Signed, expiring tokens with one key per purpose.

Invite tokens and OAuth ``state`` values are small JSON payloads signed with
HMAC-SHA256: ``<urlsafe-base64 payload>.<hex signature>``. Each purpose signs
with its own key derived from ``SECRET_KEY``, so a value issued for one
purpose (say, a Notion OAuth state) is never accepted for another (a Todoist
state or an invite).

Agent JWTs are not signed here: they still use ``SECRET_KEY`` directly (see
``app.auth.jwt``), because changing their key would sign out every agent.
"""

import base64
import hashlib
import hmac
import json
import time
from typing import Iterable, Optional

from app.config import get_settings

INVITE_TOKEN_PURPOSE = "invite-token"
NOTION_OAUTH_STATE_PURPOSE = "notion-oauth-state"
TODOIST_OAUTH_STATE_PURPOSE = "todoist-oauth-state"


def derive_key(purpose: str) -> bytes:
    """The signing key for ``purpose``: HMAC-SHA256(SECRET_KEY, "rmirror:" + purpose)."""
    secret = get_settings().secret_key.encode()
    return hmac.new(secret, b"rmirror:" + purpose.encode(), hashlib.sha256).digest()


def _signature(payload_b64: str, key: bytes) -> str:
    return hmac.new(key, payload_b64.encode(), hashlib.sha256).hexdigest()


def sign(payload: dict, key: bytes) -> str:
    """Sign ``payload`` (which should carry an integer ``exp``) with ``key``."""
    payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()
    return f"{payload_b64}.{_signature(payload_b64, key)}"


def verify(token: str, keys: Iterable[bytes]) -> Optional[dict]:
    """Return the payload if ``token`` is signed with any of ``keys`` and not expired.

    Signatures are compared in constant time. A payload without ``exp``, or
    one that is not a JSON object, is rejected. Returns None on any failure.
    """
    try:
        parts = token.split(".")
        if len(parts) != 2:
            return None
        payload_b64, signature = parts
        if not any(
            hmac.compare_digest(signature, _signature(payload_b64, key)) for key in keys
        ):
            return None
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        if not isinstance(payload, dict):
            return None
        exp = payload.get("exp")
        if not isinstance(exp, int) or isinstance(exp, bool) or exp < int(time.time()):
            return None
        return payload
    except Exception:
        return None
