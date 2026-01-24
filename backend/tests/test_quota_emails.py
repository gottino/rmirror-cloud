"""Email notification tests for quota system.

Tests TC-AUTO-10 from the test plan:
- Email sent at 90% threshold
- Email sent at 100% threshold
- No duplicate emails
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
from sqlalchemy.orm import Session

from app.models.subscription import SubscriptionTier
from app.services import quota_service
from tests.conftest import create_user_with_quota


# =============================================================================
# TC-AUTO-10: Email Triggers
# =============================================================================


def test_email_sent_at_90_percent(db: Session):
    """
    Email should be sent when quota reaches 90%.

    Expected behavior:
    - Email service called when crossing 90% threshold
    - Email contains correct user and quota data
    """
    # Setup: User with 86.7% quota used (26/30)
    user = create_user_with_quota(db, used=26, limit=30)

    # Mock email service at the import level
    with patch("app.services.quota_service.get_email_service") as mock_get_email:
        mock_email_service = MagicMock()
        mock_email_service.send_quota_warning_email.return_value = True
        mock_get_email.return_value = mock_email_service

        # Action: Consume quota to cross 90% threshold (26 -> 27 = 90%)
        quota = quota_service.consume_quota(db, user.id, amount=1)

        # Verify email sent
        mock_email_service.send_quota_warning_email.assert_called_once()

        # Verify call arguments
        call_kwargs = mock_email_service.send_quota_warning_email.call_args[1]
        assert call_kwargs["user_email"] == user.email
        assert call_kwargs["user_name"] == user.full_name or user.email
        assert call_kwargs["used"] == 27
        assert call_kwargs["limit"] == 30
        assert call_kwargs["percentage"] >= 90.0
        assert "reset_at" in call_kwargs


def test_email_sent_at_100_percent(db: Session):
    """
    Email should be sent when quota exhausted (100%).

    Expected behavior:
    - Email service called when crossing 100% threshold
    - Correct email type (quota_exceeded, not warning)
    """
    # Setup: User with 96.7% quota used (29/30)
    user = create_user_with_quota(db, used=29, limit=30)

    # Mock email service
    with patch("app.services.quota_service.get_email_service") as mock_get_email:
        mock_email_service = MagicMock()
        mock_email_service.send_quota_exceeded_email.return_value = True
        mock_get_email.return_value = mock_email_service

        # Action: Consume last quota unit (29 -> 30 = 100%)
        quota = quota_service.consume_quota(db, user.id, amount=1)

        # Verify email sent
        mock_email_service.send_quota_exceeded_email.assert_called_once()

        # Verify call arguments
        call_kwargs = mock_email_service.send_quota_exceeded_email.call_args[1]
        assert call_kwargs["user_email"] == user.email
        assert call_kwargs["user_name"] == user.full_name or user.email
        assert call_kwargs["limit"] == 30
        assert "reset_at" in call_kwargs


def test_no_duplicate_emails_after_90_percent(db: Session):
    """
    Email should only be sent once at 90% threshold.

    Expected behavior:
    - First consumption crossing 90%: email sent
    - Second consumption still >90%: NO email
    """
    # Setup: User already at 90% (27/30)
    user = create_user_with_quota(db, used=27, limit=30)

    # Mock email service
    with patch("app.services.quota_service.get_email_service") as mock_get_email:
        mock_email_service = MagicMock()
        mock_email_service.send_quota_warning_email.return_value = True
        mock_get_email.return_value = mock_email_service

        # Action: Consume more quota (27 -> 28 = 93%)
        # Should NOT send email (already past 90% threshold)
        quota = quota_service.consume_quota(db, user.id, amount=1)

        # Verify NO email sent (already sent at 90%)
        mock_email_service.send_quota_warning_email.assert_not_called()


def test_no_duplicate_emails_after_100_percent(db: Session):
    """
    Once at 100%, no more emails should be sent.

    Note: This tests the theoretical case. In practice, you can't consume
    quota beyond 100% (QuotaExceededError is raised).
    """
    # Setup: User already at 100% (30/30)
    user = create_user_with_quota(db, used=30, limit=30)

    # Mock email service
    with patch("app.utils.email.get_email_service") as mock_get_email:
        mock_email_service = MagicMock()
        mock_get_email.return_value = mock_email_service

        # Action: Try to consume more quota (should raise error)
        with pytest.raises(quota_service.QuotaExceededError):
            quota_service.consume_quota(db, user.id, amount=1)

        # Verify NO email sent (already at 100%)
        mock_email_service.send_quota_exceeded_email.assert_not_called()


def test_email_not_sent_below_90_percent(db: Session):
    """No email should be sent when quota usage is below 90%."""
    # Setup: User with 80% quota used (24/30)
    user = create_user_with_quota(db, used=24, limit=30)

    # Mock email service
    with patch("app.services.quota_service.get_email_service") as mock_get_email:
        mock_email_service = MagicMock()
        mock_email_service.send_quota_warning_email.return_value = True
        mock_get_email.return_value = mock_email_service

        # Action: Consume quota but stay below 90% (24 -> 25 = 83%)
        quota = quota_service.consume_quota(db, user.id, amount=1)

        # Verify NO email sent (still below 90%)
        mock_email_service.send_quota_warning_email.assert_not_called()
        mock_email_service.send_quota_exceeded_email.assert_not_called()


def test_email_sent_exactly_at_90_percent(db: Session):
    """Email should be sent when quota reaches exactly 90%."""
    # Setup: User with 26/30 = 86.7%
    user = create_user_with_quota(db, used=26, limit=30)

    # Mock email service
    with patch("app.services.quota_service.get_email_service") as mock_get_email:
        mock_email_service = MagicMock()
        mock_email_service.send_quota_warning_email.return_value = True
        mock_get_email.return_value = mock_email_service

        # Action: Consume to reach exactly 27/30 = 90%
        quota = quota_service.consume_quota(db, user.id, amount=1)

        # Verify email sent
        assert quota.percentage_used == 90.0
        mock_email_service.send_quota_warning_email.assert_called_once()


def test_email_crossing_both_thresholds(db: Session):
    """
    Test consuming multiple units that cross both thresholds.

    Expected behavior:
    - Crossing 90% first: warning email sent
    - Later crossing 100%: exceeded email sent
    - Two separate emails total
    """
    # Setup: User with 85% quota used (25.5/30 rounded to 26/30)
    user = create_user_with_quota(db, used=26, limit=30)

    # Mock email service
    with patch("app.services.quota_service.get_email_service") as mock_get_email:
        mock_email_service = MagicMock()
        mock_email_service.send_quota_warning_email.return_value = True
        mock_email_service.send_quota_exceeded_email.return_value = True
        mock_get_email.return_value = mock_email_service

        # Action 1: Cross 90% threshold (26 -> 27 = 90%)
        quota_service.consume_quota(db, user.id, amount=1)
        assert mock_email_service.send_quota_warning_email.call_count == 1

        # Action 2: Continue consuming (27 -> 28 = 93%)
        quota_service.consume_quota(db, user.id, amount=1)
        # No new email (still in 90-100% range)
        assert mock_email_service.send_quota_warning_email.call_count == 1

        # Action 3: Cross 100% threshold (28 -> 29 -> 30 = 100%)
        quota_service.consume_quota(db, user.id, amount=1)  # 29/30
        quota_service.consume_quota(db, user.id, amount=1)  # 30/30
        assert mock_email_service.send_quota_exceeded_email.call_count == 1

        # Total: 1 warning + 1 exceeded = 2 emails
        assert mock_email_service.send_quota_warning_email.call_count == 1
        assert mock_email_service.send_quota_exceeded_email.call_count == 1


def test_no_email_for_pro_tier(db: Session):
    """
    Pro tier users should not receive quota warning emails.

    Rationale: Pro users have 500 pages/month, warnings would be spam.
    Only free tier users get quota emails.
    """
    # Setup: Pro tier user with high quota usage
    user = create_user_with_quota(
        db,
        used=450,  # 90% of 500
        limit=500,
        tier=SubscriptionTier.PRO,
    )

    # Mock email service
    with patch("app.utils.email.get_email_service") as mock_get_email:
        mock_email_service = MagicMock()
        mock_get_email.return_value = mock_email_service

        # Action: Consume quota to cross 90% for Pro tier
        quota_service.consume_quota(db, user.id, amount=1)

        # Verify NO email sent (Pro tier exempt from quota emails)
        mock_email_service.send_quota_warning_email.assert_not_called()


def test_email_service_failure_doesnt_break_quota_consumption(db: Session):
    """
    If email service fails, quota consumption should still succeed.

    Expected behavior:
    - Email service throws exception
    - Exception is caught and logged
    - Quota still consumed successfully
    """
    # Setup: User approaching 90%
    user = create_user_with_quota(db, used=26, limit=30)

    # Mock email service to raise exception
    with patch("app.services.quota_service.get_email_service") as mock_get_email:
        mock_email_service = MagicMock()
        mock_email_service.send_quota_warning_email.side_effect = Exception(
            "Email service unavailable"
        )
        mock_get_email.return_value = mock_email_service

        # Action: Consume quota (should not raise exception)
        quota = quota_service.consume_quota(db, user.id, amount=1)

        # Verify quota still consumed despite email failure
        assert quota.used == 27
        assert quota.percentage_used == 90.0

        # Verify email was attempted
        mock_email_service.send_quota_warning_email.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
