"""User schemas."""

from datetime import datetime

from pydantic import BaseModel, EmailStr


class UserBase(BaseModel):
    """Base user schema."""

    email: EmailStr
    full_name: str | None = None


class UserCreate(UserBase):
    """User creation schema."""

    password: str


class UserUpdate(BaseModel):
    """User update schema."""

    email: EmailStr | None = None
    full_name: str | None = None
    password: str | None = None


class User(UserBase):
    """User response schema."""

    id: int
    subscription_tier: str
    is_active: bool
    is_verified: bool
    created_at: datetime
    last_login_at: datetime | None = None
    onboarding_state: str
    onboarding_started_at: datetime | None = None
    onboarding_completed_at: datetime | None = None
    agent_downloaded_at: datetime | None = None
    agent_first_connected_at: datetime | None = None
    tos_accepted_at: datetime | None = None
    tos_version: str | None = None
    privacy_accepted_at: datetime | None = None
    privacy_version: str | None = None
    is_beta_user: bool = False
    beta_enrolled_at: datetime | None = None

    class Config:
        from_attributes = True
