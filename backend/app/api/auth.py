"""Authentication endpoints.

Dashboard sessions are handled by Clerk. The only token this API mints itself
is the scoped, long-lived agent token issued by ``/auth/agent-token``. The old
email/password ``/auth/register`` and ``/auth/login`` endpoints were removed:
they bypassed Clerk and the beta gate and minted full-privilege tokens.
"""

import logging
from datetime import timedelta

from fastapi import APIRouter, Depends, Request
from slowapi import Limiter

from app.auth.clerk import get_clerk_session_user
from app.auth.jwt import create_access_token
from app.middleware.rate_limit import AUTH_ENDPOINT_LIMIT, get_rate_limit_key
from app.models.user import User
from app.schemas.auth import Token

logger = logging.getLogger(__name__)

router = APIRouter()

# Rate limiter for auth endpoints - strict limits to prevent brute force
limiter = Limiter(key_func=get_rate_limit_key)


@router.post("/agent-token", response_model=Token)
@limiter.limit(AUTH_ENDPOINT_LIMIT)
async def create_agent_token(
    request: Request,
    user: User = Depends(get_clerk_session_user),
) -> Token:
    """
    Exchange a Clerk session token for a long-lived agent JWT.

    This endpoint is called by the agent auth bridge page after
    the user signs in with Clerk. It issues a 30-day JWT that
    the agent stores in the system keychain.

    Security:
    - Requires a valid Clerk session token (get_clerk_session_user); agent
      tokens are rejected so a leaked agent token cannot mint fresh ones
    - Issued token includes 'type': 'agent' claim, enforced by the agent-scope
      guards to limit agent tokens to upload/sync/read endpoints
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
