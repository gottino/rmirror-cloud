"""Clerk authentication dependencies for FastAPI routes."""

import logging
from typing import Annotated, Optional

import jwt
from clerk_backend_sdk import ApiClient, ClientsApi, Configuration
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.middleware.request_context import user_id_var
from app.models.user import User

logger = logging.getLogger(__name__)

# HTTP Bearer token scheme
security = HTTPBearer()

# Initialize Clerk SDK (lazy-loaded)
_clerk_api_client: Optional[ApiClient] = None
_clients_api: Optional[ClientsApi] = None

# JWKS client for JWT verification (lazy-loaded)
_jwks_client: Optional[PyJWKClient] = None
_jwks_warned: bool = False  # Track if we've already warned about missing JWKS


def get_jwks_client() -> Optional[PyJWKClient]:
    """Get or create JWKS client for JWT verification.

    Returns None if CLERK_JWKS_URL is not configured (development mode).
    """
    global _jwks_client, _jwks_warned
    settings = get_settings()

    if not settings.clerk_jwks_url:
        if not settings.debug:
            raise RuntimeError(
                "CLERK_JWKS_URL is required in production. "
                "Set CLERK_JWKS_URL to your Clerk JWKS endpoint "
                "(e.g., https://your-app.clerk.accounts.dev/.well-known/jwks.json)"
            )
        if not _jwks_warned:
            logger.warning(
                "CLERK_JWKS_URL not configured - JWT signature verification disabled. "
                "This is only allowed in debug mode."
            )
            _jwks_warned = True
        return None

    if _jwks_client is None:
        _jwks_client = PyJWKClient(settings.clerk_jwks_url)
        logger.info(f"Initialized JWKS client with URL: {settings.clerk_jwks_url}")

    return _jwks_client


def get_clerk_client() -> ClientsApi:
    """Get or create Clerk ClientsApi instance."""
    global _clerk_api_client, _clients_api
    if _clients_api is None:
        settings = get_settings()
        if not settings.clerk_secret_key:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Clerk is not configured",
            )
        # Configure Clerk SDK with API key
        configuration = Configuration(
            api_key={"BearerAuth": settings.clerk_secret_key}
        )
        _clerk_api_client = ApiClient(configuration)
        _clients_api = ClientsApi(_clerk_api_client)
    return _clients_api


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
            # Agent token: verify with our secret key
            decoded = jwt.decode(
                token,
                settings.secret_key,
                algorithms=[settings.algorithm],
            )
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
                # Development mode only: Decode without signature verification but still check expiration
                decoded = jwt.decode(
                    token,
                    options={"verify_signature": False, "verify_exp": True},
                )

        # Record the token kind so downstream guards can restrict long-lived
        # agent tokens. Only tokens explicitly minted as agent tokens carry
        # ``type == "agent"``; Clerk sessions and legacy password tokens do not.
        request.state.is_agent_token = bool(decoded.get("type") == "agent")

        # Extract user ID from the token (could be Clerk ID or regular user ID)
        sub = decoded.get("sub")

        if not sub:
            raise credentials_exception

        # Try to find user by Clerk user ID first (for Clerk auth)
        user = db.query(User).filter(User.clerk_user_id == sub).first()

        # If not found, try finding by regular user ID (for password auth)
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

        # Store user_id in context for structured logging
        user_id_var.set(user.id)

        return user

    except jwt.DecodeError as e:
        logger.warning(f"JWT decode error: {e}")
        raise credentials_exception
    except jwt.ExpiredSignatureError:
        logger.debug("JWT token has expired")
        raise credentials_exception
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
