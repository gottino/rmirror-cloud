"""Authentication dependencies for FastAPI routes."""

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.auth.jwt import decode_access_token
from app.database import get_db
from app.models.user import User

# HTTP Bearer token scheme
security = HTTPBearer()


async def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    """
    Get the current authenticated user from JWT token.

    Args:
        request: Incoming request (used to record the token kind)
        credentials: HTTP Bearer credentials
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
    payload = decode_access_token(token)

    if payload is None:
        raise credentials_exception

    # Record the token kind so agent-scope guards can restrict agent tokens
    # reaching the legacy auth chain (e.g. the todos router).
    request.state.is_agent_token = bool(payload.get("type") == "agent")

    user_id_str: str | None = payload.get("sub")
    if user_id_str is None:
        raise credentials_exception

    try:
        user_id = int(user_id_str)
    except (ValueError, TypeError):
        raise credentials_exception

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise credentials_exception

    return user


async def get_current_active_user(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """
    Get the current active user.

    Args:
        current_user: Current authenticated user

    Returns:
        Current user if active

    Raises:
        HTTPException: If user is inactive
    """
    if not current_user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Inactive user")

    return current_user


async def reject_agent_token_legacy(
    request: Request,
    _current_user: Annotated[User, Depends(get_current_active_user)],
) -> None:
    """
    Router-level guard (legacy auth chain) that 403s agent tokens.

    Mirrors ``app.auth.clerk.reject_agent_token`` for routers that still use the
    legacy ``get_current_active_user`` dependency (e.g. todos). Depends on
    ``get_current_active_user`` so authentication runs first and populates
    ``request.state.is_agent_token`` before the check.
    """
    if bool(getattr(request.state, "is_agent_token", False)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Agent tokens cannot access this endpoint. Sign in to the dashboard.",
        )


async def get_obsidian_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    """
    Authenticate an Obsidian plugin request via API key.

    Looks up the hashed API key in integration_configs.api_key_hash.
    Returns the user who owns the integration.
    """
    from app.models.sync_record import IntegrationConfig
    from app.services.obsidian_service import hash_api_key

    api_key = credentials.credentials
    key_hash = hash_api_key(api_key)

    config = (
        db.query(IntegrationConfig)
        .filter(
            IntegrationConfig.api_key_hash == key_hash,
            IntegrationConfig.target_name == "obsidian",
        )
        .first()
    )

    if not config:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not config.is_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Obsidian integration is disabled",
        )

    user = db.query(User).filter(User.id == config.user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    return user
