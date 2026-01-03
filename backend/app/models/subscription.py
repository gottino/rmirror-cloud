"""Subscription model for user subscription and billing management."""

from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class SubscriptionTier(str, Enum):
    """Subscription tier options."""

    FREE = "free"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class SubscriptionStatus(str, Enum):
    """Subscription status options."""

    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELED = "canceled"
    TRIALING = "trialing"


class Subscription(Base):
    """User subscription details including billing info."""

    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True
    )

    # Subscription details
    tier: Mapped[str] = mapped_column(
        String(20), default=SubscriptionTier.FREE, nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(20), default=SubscriptionStatus.ACTIVE, nullable=False
    )

    # Billing period
    current_period_start: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Stripe integration (Phase 2 - nullable for now)
    stripe_customer_id: Mapped[str | None] = mapped_column(
        String(255), unique=True, index=True, nullable=True
    )
    stripe_subscription_id: Mapped[str | None] = mapped_column(
        String(255), unique=True, index=True, nullable=True
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="subscription")

    def __repr__(self) -> str:
        return f"<Subscription(id={self.id}, user_id={self.user_id}, tier={self.tier})>"

    @property
    def is_free_tier(self) -> bool:
        """Check if subscription is on free tier."""
        return self.tier == SubscriptionTier.FREE

    @property
    def is_pro_tier(self) -> bool:
        """Check if subscription is on pro tier."""
        return self.tier == SubscriptionTier.PRO

    @property
    def is_enterprise_tier(self) -> bool:
        """Check if subscription is on enterprise tier."""
        return self.tier == SubscriptionTier.ENTERPRISE

    @property
    def is_active(self) -> bool:
        """Check if subscription is active."""
        return self.status == SubscriptionStatus.ACTIVE
