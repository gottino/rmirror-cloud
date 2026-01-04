"""Quota management service for tracking and enforcing usage limits.

Provides functions to check, consume, and reset user quotas based on subscription tier.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.models.quota_usage import QuotaType, QuotaUsage
from app.models.subscription import Subscription, SubscriptionTier
from app.models.user import User
from app.utils.email import get_email_service

logger = logging.getLogger(__name__)


# Tier-based quota limits (pages per month)
QUOTA_LIMITS = {
    SubscriptionTier.FREE: 30,
    SubscriptionTier.PRO: 500,
    SubscriptionTier.ENTERPRISE: -1,  # Unlimited
}


class QuotaExceededError(Exception):
    """Raised when user has exhausted their quota."""

    def __init__(self, quota: QuotaUsage):
        self.quota = quota
        super().__init__(
            f"Quota exceeded: {quota.used}/{quota.limit} pages used. "
            f"Resets on {quota.reset_at.strftime('%Y-%m-%d')}."
        )


def get_or_create_quota(
    db: Session,
    user_id: int,
    quota_type: str = QuotaType.OCR,
) -> QuotaUsage:
    """
    Get existing quota or create new one for user.

    Args:
        db: Database session
        user_id: User ID
        quota_type: Type of quota ('ocr')

    Returns:
        QuotaUsage instance

    Example:
        >>> quota = get_or_create_quota(db, user_id=42)
        >>> print(f"{quota.used}/{quota.limit}")
    """
    # Try to find existing quota
    quota = (
        db.query(QuotaUsage)
        .filter(
            QuotaUsage.user_id == user_id,
            QuotaUsage.quota_type == quota_type,
        )
        .first()
    )

    if quota:
        # Check if quota needs reset (period has ended)
        if datetime.utcnow() >= quota.reset_at:
            quota = reset_quota(db, user_id, quota_type)
        return quota

    # Create new quota for user
    # Get user's subscription to determine limit
    subscription = db.query(Subscription).filter(
        Subscription.user_id == user_id
    ).first()

    if not subscription:
        raise ValueError(f"No subscription found for user {user_id}")

    # Determine quota limit based on tier
    tier = subscription.tier
    limit = QUOTA_LIMITS.get(tier, QUOTA_LIMITS[SubscriptionTier.FREE])

    # Calculate reset date (30 days from now)
    now = datetime.utcnow()
    reset_at = now + timedelta(days=30)

    quota = QuotaUsage(
        user_id=user_id,
        quota_type=quota_type,
        limit=limit,
        used=0,
        reset_at=reset_at,
        period_start=now,
    )

    db.add(quota)
    db.commit()
    db.refresh(quota)

    return quota


def check_quota(
    db: Session,
    user_id: int,
    quota_type: str = QuotaType.OCR,
    amount: int = 1,
) -> bool:
    """
    Check if user has sufficient quota remaining.

    Args:
        db: Database session
        user_id: User ID
        quota_type: Type of quota to check
        amount: Amount of quota needed

    Returns:
        True if quota available, False if exhausted

    Example:
        >>> if check_quota(db, user_id=42, amount=1):
        ...     # Process page
        ...     consume_quota(db, user_id=42, amount=1)
    """
    quota = get_or_create_quota(db, user_id, quota_type)

    # Enterprise tier has unlimited quota
    if quota.limit == -1:
        return True

    # Check if user has enough remaining quota
    return (quota.used + amount) <= quota.limit


def consume_quota(
    db: Session,
    user_id: int,
    quota_type: str = QuotaType.OCR,
    amount: int = 1,
) -> QuotaUsage:
    """
    Consume quota for user.

    Increments the 'used' counter by the specified amount.
    Raises QuotaExceededError if quota would be exceeded.
    Sends email notifications when crossing 90% or 100% thresholds.

    Args:
        db: Database session
        user_id: User ID
        quota_type: Type of quota to consume
        amount: Amount of quota to consume

    Returns:
        Updated QuotaUsage instance

    Raises:
        QuotaExceededError: If consuming would exceed quota limit

    Example:
        >>> try:
        ...     quota = consume_quota(db, user_id=42, amount=1)
        ...     print(f"Consumed. Remaining: {quota.quota_remaining}")
        ... except QuotaExceededError as e:
        ...     print(f"Quota exhausted: {e}")
    """
    quota = get_or_create_quota(db, user_id, quota_type)

    # Enterprise tier has unlimited quota
    if quota.limit == -1:
        # Don't increment counter for unlimited tier
        return quota

    # Check if consumption would exceed limit
    if (quota.used + amount) > quota.limit:
        raise QuotaExceededError(quota)

    # Calculate percentage before consumption
    percentage_before = quota.percentage_used

    # Increment used counter
    quota.used += amount
    quota.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(quota)

    # Calculate percentage after consumption
    percentage_after = quota.percentage_used

    # Send email notifications when crossing thresholds
    # Only send emails for free tier users (to avoid spamming Pro users)
    subscription = db.query(Subscription).filter(
        Subscription.user_id == user_id
    ).first()

    if subscription and subscription.tier == SubscriptionTier.FREE:
        _send_quota_notification_if_needed(
            db=db,
            user_id=user_id,
            quota=quota,
            percentage_before=percentage_before,
            percentage_after=percentage_after,
        )

    return quota


def _send_quota_notification_if_needed(
    db: Session,
    user_id: int,
    quota: QuotaUsage,
    percentage_before: float,
    percentage_after: float,
) -> None:
    """
    Send quota notification email if threshold crossed.

    Sends warning at 90% and exceeded at 100%.
    Only sends once per threshold to avoid spam.

    Args:
        db: Database session
        user_id: User ID
        quota: QuotaUsage instance
        percentage_before: Percentage before consumption
        percentage_after: Percentage after consumption
    """
    # Get user info for email
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        logger.warning(f"User {user_id} not found for quota notification")
        return

    email_service = get_email_service()

    # Format reset date for email
    reset_date = quota.reset_at.strftime("%B %d, %Y")

    # Check if crossed 100% threshold (quota exhausted)
    if percentage_before < 100.0 and percentage_after >= 100.0:
        logger.info(f"Sending quota exceeded email to user {user_id}")
        try:
            email_service.send_quota_exceeded_email(
                user_email=user.email,
                user_name=user.full_name or user.email,
                limit=quota.limit,
                reset_at=reset_date,
            )
        except Exception as e:
            logger.error(f"Failed to send quota exceeded email: {e}")

    # Check if crossed 90% threshold (warning)
    elif percentage_before < 90.0 and percentage_after >= 90.0:
        logger.info(f"Sending quota warning email to user {user_id}")
        try:
            email_service.send_quota_warning_email(
                user_email=user.email,
                user_name=user.full_name or user.email,
                used=quota.used,
                limit=quota.limit,
                percentage=percentage_after,
                reset_at=reset_date,
            )
        except Exception as e:
            logger.error(f"Failed to send quota warning email: {e}")


def reset_quota(
    db: Session,
    user_id: int,
    quota_type: str = QuotaType.OCR,
) -> QuotaUsage:
    """
    Reset quota for user (start new billing period).

    Sets 'used' back to 0 and updates reset_at to next period.

    Args:
        db: Database session
        user_id: User ID
        quota_type: Type of quota to reset

    Returns:
        Reset QuotaUsage instance

    Example:
        >>> quota = reset_quota(db, user_id=42)
        >>> print(f"Reset. New period: {quota.period_start} to {quota.reset_at}")
    """
    quota = get_or_create_quota(db, user_id, quota_type)

    # Reset usage counter
    quota.used = 0

    # Update period dates
    now = datetime.utcnow()
    quota.period_start = now
    quota.reset_at = now + timedelta(days=30)
    quota.updated_at = now

    db.commit()
    db.refresh(quota)

    return quota


def get_quota_status(
    db: Session,
    user_id: int,
    quota_type: str = QuotaType.OCR,
) -> dict:
    """
    Get detailed quota status for user.

    Returns dict with quota information for display in UI.

    Args:
        db: Database session
        user_id: User ID
        quota_type: Type of quota

    Returns:
        Dict with keys: limit, used, remaining, percentage_used, is_exhausted,
        is_near_limit, reset_at, period_start

    Example:
        >>> status = get_quota_status(db, user_id=42)
        >>> print(f"Used: {status['used']}/{status['limit']}")
        >>> print(f"Resets: {status['reset_at']}")
    """
    quota = get_or_create_quota(db, user_id, quota_type)

    return {
        "limit": quota.limit,
        "used": quota.used,
        "remaining": quota.quota_remaining,
        "percentage_used": quota.percentage_used,
        "is_exhausted": quota.is_exhausted,
        "is_near_limit": quota.is_near_limit,
        "reset_at": quota.reset_at.isoformat(),
        "period_start": quota.period_start.isoformat(),
        "quota_type": quota.quota_type,
    }


def update_quota_limit(
    db: Session,
    user_id: int,
    new_tier: str,
    quota_type: str = QuotaType.OCR,
) -> QuotaUsage:
    """
    Update quota limit when user changes subscription tier.

    Called when user upgrades/downgrades subscription.

    Args:
        db: Database session
        user_id: User ID
        new_tier: New subscription tier
        quota_type: Type of quota to update

    Returns:
        Updated QuotaUsage instance

    Example:
        >>> # User upgraded to Pro
        >>> quota = update_quota_limit(db, user_id=42, new_tier='pro')
        >>> print(f"New limit: {quota.limit}")
    """
    quota = get_or_create_quota(db, user_id, quota_type)

    # Get new limit based on tier
    new_limit = QUOTA_LIMITS.get(new_tier, QUOTA_LIMITS[SubscriptionTier.FREE])

    # Update limit
    quota.limit = new_limit
    quota.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(quota)

    return quota
