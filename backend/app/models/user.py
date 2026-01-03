"""User model for authentication and subscription management."""

from datetime import datetime
from enum import Enum

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class SubscriptionTier(str, Enum):
    """Subscription tier options."""

    FREE = "free"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class OnboardingState(str, Enum):
    """User onboarding progress states."""

    SIGNED_UP = "signed_up"
    AGENT_DOWNLOADED = "agent_downloaded"
    AGENT_CONNECTED = "agent_connected"
    FOLDER_CONFIGURED = "folder_configured"
    FIRST_SYNC_STARTED = "first_sync_started"
    FIRST_SYNC_COMPLETED = "first_sync_completed"
    COMPLETE = "complete"


class User(Base):
    """User accounts with authentication and subscription info."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)

    # Authentication - either Clerk or password-based
    clerk_user_id: Mapped[str | None] = mapped_column(String(255), unique=True, index=True, nullable=True)
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)

    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Subscription
    subscription_tier: Mapped[str] = mapped_column(
        String(20), default=SubscriptionTier.FREE, nullable=False
    )
    subscription_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # API Key
    api_key_hash: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Onboarding
    onboarding_state: Mapped[str] = mapped_column(
        String(30), default=OnboardingState.SIGNED_UP, nullable=False
    )
    onboarding_started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    onboarding_completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    agent_downloaded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    agent_first_connected_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Relationships
    subscription: Mapped["Subscription"] = relationship(
        "Subscription", back_populates="user", cascade="all, delete-orphan", uselist=False
    )
    quota_usages: Mapped[list["QuotaUsage"]] = relationship(
        "QuotaUsage", back_populates="user", cascade="all, delete-orphan"
    )
    notebooks: Mapped[list["Notebook"]] = relationship(
        "Notebook", back_populates="user", cascade="all, delete-orphan"
    )
    highlights: Mapped[list["Highlight"]] = relationship(
        "Highlight", back_populates="user", cascade="all, delete-orphan"
    )
    todos: Mapped[list["Todo"]] = relationship(
        "Todo", back_populates="user", cascade="all, delete-orphan"
    )
    connectors: Mapped[list["Connector"]] = relationship(
        "Connector", back_populates="user", cascade="all, delete-orphan"
    )
    processing_jobs: Mapped[list["ProcessingJob"]] = relationship(
        "ProcessingJob", back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email={self.email})>"

    @property
    def ocr_quota(self) -> "QuotaUsage | None":
        """Get the OCR quota for this user."""
        for quota in self.quota_usages:
            if quota.quota_type == "ocr":
                return quota
        return None
