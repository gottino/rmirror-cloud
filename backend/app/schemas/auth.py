"""Authentication schemas."""

from pydantic import BaseModel


class Token(BaseModel):
    """JWT token response."""

    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    """Data stored in JWT token."""

    user_id: int | None = None


class LoginRequest(BaseModel):
    """Login request."""

    email: str
    password: str
