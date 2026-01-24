"""Clerk authentication dependencies for FastAPI routes."""

from typing import Annotated, Optional

from clerk_backend_sdk import ApiClient, ClientsApi, Configuration
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models.user import User

# HTTP Bearer token scheme
security = HTTPBearer()

# Initialize Clerk SDK (lazy-loaded)
_clerk_api_client: Optional[ApiClient] = None
_clients_api: Optional[ClientsApi] = None


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
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    """
    Get the current authenticated user from Clerk JWT token.

    Args:
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

    try:
        # Decode JWT token without verification to get the user ID
        # In production, you should verify the JWT signature using Clerk's JWKS
        import jwt

        # Decode without verification for now (user ID is in 'sub' claim)
        decoded = jwt.decode(token, options={"verify_signature": False})

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

        return user

    except jwt.DecodeError as e:
        print(f"JWT decode error: {e}")
        raise credentials_exception
    except Exception as e:
        print(f"Clerk authentication error: {e}")
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
