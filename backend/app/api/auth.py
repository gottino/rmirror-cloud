"""Authentication endpoints.

Dashboard sessions are handled by Clerk. The only token this API mints itself
is the scoped, long-lived agent token issued by ``/auth/agent-token``. The old
email/password ``/auth/register`` and ``/auth/login`` endpoints were removed:
they bypassed Clerk and the beta gate and minted full-privilege tokens.
"""

import logging
from datetime import timedelta

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.auth.clerk import get_clerk_session_user
from app.auth.jwt import create_access_token
from app.database import get_db
from app.middleware.rate_limit import AUTH_ENDPOINT_LIMIT, limiter
from app.models.user import User
from app.schemas.auth import Token

logger = logging.getLogger(__name__)

router = APIRouter()


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
    - Token carries the user's current ``agent_token_version`` as ``ver``;
      ``/auth/agent-token/revoke`` invalidates it
    - All issuances are logged for audit
    - Signed with SECRET_KEY directly (not a per-purpose derived key):
      changing the key would sign out every installed agent
    """
    # Audit log: who requested an agent token and from where
    client_ip = request.client.host if request.client else "unknown"
    logger.info(
        f"Agent token issued: user_id={user.id}, email={user.email}, ip={client_ip}"
    )

    access_token = create_access_token(
        data={"sub": str(user.id), "type": "agent", "ver": user.agent_token_version},
        expires_delta=timedelta(days=30),
    )
    return Token(access_token=access_token, token_type="bearer")


@router.post("/agent-token/revoke")
@limiter.limit(AUTH_ENDPOINT_LIMIT)
async def revoke_agent_tokens(
    request: Request,
    user: User = Depends(get_clerk_session_user),
    db: Session = Depends(get_db),
) -> dict:
    """
    Revoke ALL agent tokens of the signed-in user.

    Increments the user's ``agent_token_version``; every agent token issued
    before this call stops authenticating (401). Tokens are not tracked one by
    one, so this signs out every connected agent of the user: each one must
    sign in again to get a new token.

    Requires a Clerk session (get_clerk_session_user). Agent tokens cannot
    call this endpoint, so a leaked agent token cannot revoke or otherwise act
    beyond its scope; an agent signing out can only delete its local token.
    """
    db.query(User).filter(User.id == user.id).update(
        {User.agent_token_version: User.agent_token_version + 1},
        synchronize_session=False,
    )
    db.commit()
    db.refresh(user)

    client_ip = request.client.host if request.client else "unknown"
    logger.info(
        f"Agent tokens revoked: user_id={user.id}, "
        f"version={user.agent_token_version}, ip={client_ip}"
    )
    return {"revoked": True}
