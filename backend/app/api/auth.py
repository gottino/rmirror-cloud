"""Authentication endpoints."""

import logging
from datetime import datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from slowapi import Limiter
from sqlalchemy.orm import Session

from app.auth import get_password_hash, verify_password
from app.auth.clerk import get_clerk_user
from app.auth.jwt import create_access_token
from app.database import get_db
from app.middleware.rate_limit import AUTH_ENDPOINT_LIMIT, get_rate_limit_key
from app.models.user import User
from app.schemas.auth import LoginRequest, Token
from app.schemas.user import User as UserSchema
from app.schemas.user import UserCreate

logger = logging.getLogger(__name__)

router = APIRouter()

# Rate limiter for auth endpoints - strict limits to prevent brute force
limiter = Limiter(key_func=get_rate_limit_key)


@router.post("/register", response_model=UserSchema, status_code=status.HTTP_201_CREATED)
@limiter.limit(AUTH_ENDPOINT_LIMIT)
async def register(
    request: Request,
    user_data: UserCreate,
    db: Annotated[Session, Depends(get_db)],
):
    """
    Register a new user.

    Args:
        user_data: User registration data
        db: Database session

    Returns:
        Created user

    Raises:
        HTTPException: If email already exists
    """
    # Check if user exists
    existing_user = db.query(User).filter(User.email == user_data.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    # Create new user
    hashed_password = get_password_hash(user_data.password)
    db_user = User(
        email=user_data.email,
        full_name=user_data.full_name,
        hashed_password=hashed_password,
    )

    db.add(db_user)
    db.commit()
    db.refresh(db_user)

    return db_user


@router.post("/login", response_model=Token)
@limiter.limit(AUTH_ENDPOINT_LIMIT)
async def login(
    request: Request,
    login_data: LoginRequest,
    db: Annotated[Session, Depends(get_db)],
):
    """
    Login and get access token.

    Args:
        login_data: Login credentials
        db: Database session

    Returns:
        JWT access token

    Raises:
        HTTPException: If credentials are invalid
    """
    # Find user
    user = db.query(User).filter(User.email == login_data.email).first()

    # Verify credentials
    if not user or not verify_password(login_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check if user is active
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive",
        )

    # Update last login
    user.last_login_at = datetime.utcnow()
    db.commit()

    # Create access token
    access_token = create_access_token(data={"sub": str(user.id)})

    return Token(access_token=access_token)


@router.post("/agent-token", response_model=Token)
@limiter.limit(AUTH_ENDPOINT_LIMIT)
async def create_agent_token(
    request: Request,
    user: User = Depends(get_clerk_user),
) -> Token:
    """
    Exchange a Clerk session token for a long-lived agent JWT.

    This endpoint is called by the agent auth bridge page after
    the user signs in with Clerk. It issues a 30-day JWT that
    the agent stores in the system keychain.

    Security:
    - Requires valid Clerk session token (verified by get_clerk_user)
    - Issued token includes 'type': 'agent' claim for audit purposes
    - Token is bound to user ID, not Clerk session
    - All issuances are logged for audit
    """
    # Audit log: who requested an agent token and from where
    client_ip = request.client.host if request.client else "unknown"
    logger.info(
        f"Agent token issued: user_id={user.id}, email={user.email}, ip={client_ip}"
    )

    access_token = create_access_token(
        data={"sub": str(user.id), "type": "agent"},
        expires_delta=timedelta(days=30),
    )
    return Token(access_token=access_token, token_type="bearer")
