"""Clerk authentication dependencies for FastAPI routes."""

from typing import Annotated, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from clerk_backend_sdk import Client
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models.user import User

# HTTP Bearer token scheme
security = HTTPBearer()

# Initialize Clerk SDK (lazy-loaded)
_clerk_client: Optional[Client] = None


def get_clerk_client() -> Client:
    """Get or create Clerk client instance."""
    global _clerk_client
    if _clerk_client is None:
        settings = get_settings()
        if not settings.clerk_secret_key:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Clerk is not configured",
            )
        _clerk_client = Client(bearer_auth=settings.clerk_secret_key)
    return _clerk_client


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
        # Verify the token with Clerk
        clerk = get_clerk_client()
        session = clerk.sessions.verify_token(token)

        # Extract Clerk user ID from the verified session
        clerk_user_id = session.get("sub")

        if not clerk_user_id:
            raise credentials_exception

        # Find user in database by Clerk user ID
        user = db.query(User).filter(User.clerk_user_id == clerk_user_id).first()

        if user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found. Please complete registration via webhook.",
            )

        return user

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
