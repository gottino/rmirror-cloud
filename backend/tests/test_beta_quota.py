"""Test cases for beta user quota functionality.

Tests beta-aware quota limits, resets, tier upgrades, status reporting,
and webhook behavior for beta user flagging.
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from app.models.quota_usage import QuotaType, QuotaUsage
from app.models.subscription import Subscription, SubscriptionStatus, SubscriptionTier
from app.models.user import User
from app.services.quota_service import (
    BETA_QUOTA_LIMIT,
    QUOTA_LIMITS,
    _get_quota_limit,
    get_or_create_quota,
    get_quota_status,
    reset_quota,
    update_quota_limit,
)


def _create_beta_user(
    db: Session,
    email: str = "beta@test.com",
    tier: str = SubscriptionTier.FREE,
    is_beta: bool = True,
) -> User:
    """Helper to create a beta user with subscription."""
    user = User(
        email=email,
        full_name="Beta Tester",
        clerk_user_id=f"clerk_beta_{datetime.utcnow().timestamp()}",
        subscription_tier=tier,
        is_active=True,
        is_verified=True,
        is_beta_user=is_beta,
        beta_enrolled_at=datetime.utcnow() if is_beta else None,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    subscription = Subscription(
        user_id=user.id,
        tier=tier,
        status=SubscriptionStatus.ACTIVE,
        current_period_start=datetime.utcnow(),
        current_period_end=datetime.utcnow() + timedelta(days=30),
    )
    db.add(subscription)
    db.commit()

    return user


def test_beta_user_gets_200_limit_on_quota_creation(db: Session):
    """Beta user on FREE tier gets limit=200 when quota is first created."""
    user = _create_beta_user(db)

    quota = get_or_create_quota(db, user.id)

    assert quota.limit == BETA_QUOTA_LIMIT
    assert quota.limit == 200
    assert quota.used == 0


def test_non_beta_user_gets_30_limit(db: Session):
    """Regular FREE user (non-beta) gets limit=30."""
    user = _create_beta_user(db, email="regular@test.com", is_beta=False)

    quota = get_or_create_quota(db, user.id)

    assert quota.limit == QUOTA_LIMITS[SubscriptionTier.FREE]
    assert quota.limit == 30


def test_beta_user_quota_reset_preserves_200_limit(db: Session):
    """Reset doesn't downgrade beta user from 200 to 30."""
    user = _create_beta_user(db)

    # Create initial quota
    quota = get_or_create_quota(db, user.id)
    assert quota.limit == 200

    # Simulate some usage
    quota.used = 150
    db.commit()

    # Reset quota
    quota = reset_quota(db, user.id, trigger_retroactive_processing=False)

    assert quota.used == 0
    assert quota.limit == 200


def test_beta_pro_user_gets_pro_limit(db: Session):
    """Beta user who upgrades to PRO gets 500, not 200."""
    user = _create_beta_user(db, email="betapro@test.com", tier=SubscriptionTier.PRO)

    quota = get_or_create_quota(db, user.id)

    assert quota.limit == QUOTA_LIMITS[SubscriptionTier.PRO]
    assert quota.limit == 500


def test_quota_status_includes_beta_flag(db: Session):
    """get_quota_status() returns is_beta: True for beta users."""
    user = _create_beta_user(db)

    # Create quota first
    get_or_create_quota(db, user.id)

    status = get_quota_status(db, user.id)

    assert status["is_beta"] is True
    assert status["limit"] == 200


def test_quota_status_non_beta_flag(db: Session):
    """get_quota_status() returns is_beta: False for non-beta users."""
    user = _create_beta_user(db, email="nonbeta@test.com", is_beta=False)

    get_or_create_quota(db, user.id)

    status = get_quota_status(db, user.id)

    assert status["is_beta"] is False
    assert status["limit"] == 30


def test_update_quota_limit_respects_beta_on_downgrade(db: Session):
    """When a beta PRO user downgrades to FREE, they get 200 (not 30)."""
    user = _create_beta_user(db, email="downgrade@test.com", tier=SubscriptionTier.PRO)

    # Create quota at PRO level
    quota = get_or_create_quota(db, user.id)
    assert quota.limit == 500

    # Downgrade to FREE
    quota = update_quota_limit(db, user.id, SubscriptionTier.FREE)

    assert quota.limit == 200


@pytest.mark.asyncio
async def test_webhook_flags_beta_user(db: Session):
    """New user created via Clerk webhook gets is_beta_user=True when beta_signup_enabled=True."""
    from app.api.webhooks.clerk import handle_user_created

    mock_settings = MagicMock()
    mock_settings.beta_signup_enabled = True

    webhook_data = {
        "id": "clerk_webhook_beta_test",
        "email_addresses": [
            {"id": "email_1", "email_address": "webhook_beta@test.com"}
        ],
        "primary_email_address_id": "email_1",
        "first_name": "Beta",
        "last_name": "Tester",
    }

    with patch("app.api.webhooks.clerk.get_settings", return_value=mock_settings), \
         patch("app.api.webhooks.clerk.get_email_service") as mock_email:
        mock_email.return_value.send_welcome_email.return_value = True
        await handle_user_created(webhook_data, db)

    user = db.query(User).filter(User.email == "webhook_beta@test.com").first()
    assert user is not None
    assert user.is_beta_user is True
    assert user.beta_enrolled_at is not None


@pytest.mark.asyncio
async def test_webhook_no_beta_flag_when_disabled(db: Session):
    """New user NOT flagged as beta when beta_signup_enabled=False."""
    from app.api.webhooks.clerk import handle_user_created

    mock_settings = MagicMock()
    mock_settings.beta_signup_enabled = False

    webhook_data = {
        "id": "clerk_webhook_nobeta_test",
        "email_addresses": [
            {"id": "email_1", "email_address": "webhook_nobeta@test.com"}
        ],
        "primary_email_address_id": "email_1",
        "first_name": "Regular",
        "last_name": "User",
    }

    with patch("app.api.webhooks.clerk.get_settings", return_value=mock_settings), \
         patch("app.api.webhooks.clerk.get_email_service") as mock_email:
        mock_email.return_value.send_welcome_email.return_value = True
        await handle_user_created(webhook_data, db)

    user = db.query(User).filter(User.email == "webhook_nobeta@test.com").first()
    assert user is not None
    assert user.is_beta_user is False
    assert user.beta_enrolled_at is None
