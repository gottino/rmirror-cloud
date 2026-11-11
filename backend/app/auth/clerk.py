"""Clerk authentication dependencies for FastAPI routes."""

import logging
from typing import Annotated, Optional

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.middleware.rate_limit import set_rate_limit_user
from app.middleware.request_context import user_id_var
from app.models.user import User

logger = logging.getLogger(__name__)

# HTTP Bearer token scheme
security = HTTPBearer()

# JWKS client for JWT verification (lazy-loaded)
_jwks_client: Optional[PyJWKClient] = None
_jwks_warned: bool = False  # Track if we've already warned about missing JWKS


def get_jwks_client() -> Optional[PyJWKClient]:
    """Get or create JWKS client for JWT verification.

    Returns None if CLERK_JWKS_URL is not configured and
    ALLOW_UNVERIFIED_CLERK_TOKENS is set (local development only).
    """
    global _jwks_client, _jwks_warned
    settings = get_settings()

    if not settings.clerk_jwks_url:
        if not settings.allow_unverified_clerk_tokens:
            raise RuntimeError(
                "CLERK_JWKS_URL is required. "
                "Set CLERK_JWKS_URL to your Clerk JWKS endpoint "
                "(e.g., https://your-app.clerk.accounts.dev/.well-known/jwks.json)"
            )
        if not _jwks_warned:
            logger.warning(
                "CLERK_JWKS_URL not configured - JWT signature verification disabled "
                "because ALLOW_UNVERIFIED_CLERK_TOKENS is set (local development only)."
            )
            _jwks_warned = True
        return None

    if _jwks_client is None:
        _jwks_client = PyJWKClient(settings.clerk_jwks_url)
        logger.info(f"Initialized JWKS client with URL: {settings.clerk_jwks_url}")

    return _jwks_client


_JWKS_SUFFIX = "/.well-known/jwks.json"
_issuer_warned: bool = False
_AZP_WARNED_MAX = 50
_azp_warned: set[str] = set()  # distinct unexpected azp values already logged


def get_expected_issuer(settings) -> Optional[str]:
    """The ``iss`` value Clerk session tokens must carry, or None to skip the check.

    CLERK_ISSUER wins. Otherwise the issuer is derived from CLERK_JWKS_URL,
    which for a Clerk instance is "<issuer>/.well-known/jwks.json". If neither
    gives an issuer (no Clerk configured, or a JWKS URL of another shape) the
    check is skipped rather than guessed.
    """
    global _issuer_warned
    if settings.clerk_issuer:
        return settings.clerk_issuer.rstrip("/")
    jwks_url = settings.clerk_jwks_url
    if not jwks_url:
        return None
    if jwks_url.endswith(_JWKS_SUFFIX):
        return jwks_url[: -len(_JWKS_SUFFIX)].rstrip("/")
    if not _issuer_warned:
        logger.warning(
            "Cannot derive the Clerk issuer from CLERK_JWKS_URL; set CLERK_ISSUER "
            "to enable issuer validation of Clerk tokens."
        )
        _issuer_warned = True
    return None


def _warn_unlisted_azp(azp: str, settings) -> None:
    """Log once per distinct ``azp`` (bounded) that is outside the default origins."""
    value = azp.rstrip("/")
    if value in settings.default_authorized_parties() or value in _azp_warned:
        return
    if len(_azp_warned) >= _AZP_WARNED_MAX:
        return
    _azp_warned.add(value)
    logger.warning(
        "Clerk token authorised party %r is not among the expected origins "
        "(CORS_ORIGINS, DASHBOARD_URL); it was accepted. Set "
        "CLERK_AUTHORIZED_PARTIES to enforce an allow-list.",
        value[:200],
    )


def validate_clerk_claims(decoded: dict, settings) -> bool:
    """Check the issuer and authorised party of a decoded Clerk session token.

    ``iss`` must equal the expected issuer (when one is known). ``azp`` is only
    enforced when CLERK_AUTHORIZED_PARTIES is set to a non-empty list: then a
    token's ``azp``, if it has one, must be in it. When unset, an ``azp`` outside
    the derived default origins is accepted but logged once per distinct value.
    Clerk omits ``azp`` in some flows, so a token without it is always accepted.
    """
    expected_issuer = get_expected_issuer(settings)
    if expected_issuer is not None:
        issuer = decoded.get("iss")
        if not isinstance(issuer, str) or issuer.rstrip("/") != expected_issuer:
            logger.warning("Rejected Clerk token with unexpected issuer")
            return False

    azp = decoded.get("azp")
    if azp is not None:
        configured = settings.clerk_authorized_parties
        if configured:
            allowed = {p.rstrip("/") for p in configured}
            if not isinstance(azp, str) or azp.rstrip("/") not in allowed:
                logger.warning("Rejected Clerk token with unexpected authorised party")
                return False
        elif isinstance(azp, str):
            _warn_unlisted_azp(azp, settings)

    return True


def _agent_token_version_matches(decoded: dict, user: User) -> bool:
    """True when an agent token's ``ver`` equals the user's current version.

    Tokens issued before revocation existed have no ``ver`` claim; they count
    as version 0 and keep working until the user first revokes.
    """
    ver = decoded.get("ver", 0)
    if not isinstance(ver, int) or isinstance(ver, bool):
        return False
    return ver == (user.agent_token_version or 0)


async def get_clerk_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    """
    Get the current authenticated user from Clerk JWT token.

    Args:
        request: Incoming request (used to record the token kind)
        credentials: HTTP Bearer credentials containing Clerk session token
        db: Database session

    Returns:
        Current user

    Raises:
        HTTPException: If token is invalid or user not found
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    token = credentials.credentials
    settings = get_settings()

    try:
        # Check if this is an agent token (HS256, signed with our secret key)
        # by peeking at the header before full verification
        try:
            header = jwt.get_unverified_header(token)
        except jwt.DecodeError:
            raise credentials_exception

        if header.get("alg") == "HS256":
            # Agent token: verify with our secret key. Agent JWTs keep using
            # SECRET_KEY itself, not a per-purpose derived key (app.auth.signing):
            # switching keys would sign out every installed agent.
            decoded = jwt.decode(
                token,
                settings.secret_key,
                algorithms=[settings.algorithm],
            )
            # The only HS256 tokens this API issues are scoped agent tokens.
            # Anything else signed with SECRET_KEY (old password-login tokens,
            # or tokens minted for another purpose) must not authenticate,
            # because it would be treated as a full dashboard session.
            if decoded.get("type") != "agent":
                logger.warning("Rejected HS256 token without type=agent")
                raise credentials_exception
        else:
            # Clerk token: verify with JWKS
            jwks_client = get_jwks_client()

            if jwks_client:
                # Production mode: Verify JWT signature using Clerk's JWKS
                try:
                    signing_key = jwks_client.get_signing_key_from_jwt(token)
                    decoded = jwt.decode(
                        token,
                        signing_key.key,
                        algorithms=["RS256"],
                        options={"verify_aud": False}  # Clerk tokens don't always have audience
                    )
                except jwt.exceptions.PyJWKClientError as e:
                    logger.error(f"JWKS client error: {e}")
                    raise credentials_exception
                except jwt.exceptions.InvalidSignatureError:
                    logger.warning("JWT signature verification failed - possible token tampering")
                    raise credentials_exception
            else:
                # ALLOW_UNVERIFIED_CLERK_TOKENS (SQLite dev only): no signature check, still check expiry
                decoded = jwt.decode(
                    token,
                    options={"verify_signature": False, "verify_exp": True},
                )

            if not validate_clerk_claims(decoded, settings):
                raise credentials_exception

        # Record the token kind so downstream guards can restrict long-lived
        # agent tokens. Only tokens explicitly minted as agent tokens carry
        # ``type == "agent"``; Clerk sessions do not.
        request.state.is_agent_token = bool(decoded.get("type") == "agent")

        # Extract user ID: a Clerk user ID, or our integer user ID for agent tokens
        sub = decoded.get("sub")

        if not sub:
            raise credentials_exception

        # Try to find user by Clerk user ID first (for Clerk auth)
        user = db.query(User).filter(User.clerk_user_id == sub).first()

        # If not found, try our integer user ID (agent tokens)
        if user is None:
            try:
                user_id = int(sub)
                user = db.query(User).filter(User.id == user_id).first()
            except (ValueError, TypeError):
                pass  # Not a valid integer, was probably a Clerk ID

        if user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found. Please complete registration via webhook.",
            )

        if request.state.is_agent_token and not _agent_token_version_matches(decoded, user):
            logger.warning("Rejected revoked agent token: user_id=%s", user.id)
            raise credentials_exception

        # Store user_id in context for structured logging
        user_id_var.set(user.id)
        # Key this request's rate limits by user instead of IP
        set_rate_limit_user(request, user.id)

        return user

    except jwt.DecodeError as e:
        logger.warning(f"JWT decode error: {e}")
        raise credentials_exception
    except jwt.ExpiredSignatureError:
        logger.debug("JWT token has expired")
        raise credentials_exception
    except HTTPException:
        # Already the intended response (e.g. 401, or 404 "User not found")
        raise
    except Exception as e:
        logger.error(f"Clerk authentication error: {e}")
        raise credentials_exception


async def get_clerk_active_user(
    current_user: Annotated[User, Depends(get_clerk_user)],
) -> User:
    """
    Get the current active Clerk user.

    Args:
        current_user: Current authenticated user

    Returns:
        Current user if active

    Raises:
        HTTPException: If user is inactive
    """
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user",
        )

    return current_user


# Detail message shared by the agent-token guards below.
_AGENT_TOKEN_FORBIDDEN = (
    "Agent tokens cannot access this endpoint. Sign in to the dashboard."
)


def _is_agent_request(request: Request) -> bool:
    """True when the current request was authenticated with an agent token."""
    return bool(getattr(request.state, "is_agent_token", False))


async def get_clerk_session_user(
    request: Request,
    current_user: Annotated[User, Depends(get_clerk_active_user)],
) -> User:
    """
    Like ``get_clerk_active_user`` but rejects long-lived agent tokens.

    Use on destructive or account-management endpoints (delete, export,
    integration management, token minting) that the Mac agent never calls, so a
    leaked agent token cannot perform them. The agent is limited to
    upload/sync/read endpoints, which keep using ``get_clerk_active_user``.
    """
    if _is_agent_request(request):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=_AGENT_TOKEN_FORBIDDEN,
        )
    return current_user


async def reject_agent_token(
    request: Request,
    _current_user: Annotated[User, Depends(get_clerk_active_user)],
) -> None:
    """
    Router-level guard that 403s agent tokens after authenticating the request.

    Apply via ``APIRouter(dependencies=[Depends(reject_agent_token)])`` to
    routers the agent never calls (integrations, notion, todoist, account).
    Depending on ``get_clerk_active_user`` guarantees auth runs first, so
    ``request.state.is_agent_token`` is populated before the check.
    """
    if _is_agent_request(request):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=_AGENT_TOKEN_FORBIDDEN,
        )
