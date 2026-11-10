"""Authentication dependencies for FastAPI routes.

Dashboard and agent requests authenticate through ``app.auth.clerk``. This
module only holds the Obsidian plugin's API-key dependency.
"""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User

# HTTP Bearer token scheme
security = HTTPBearer()


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
