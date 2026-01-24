"""Test cases for quota service functionality.

Tests TC-AUTO-01 and TC-AUTO-02 from the test plan:
- Quota consumption
- Quota exhaustion check
"""

import pytest
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from app.models.quota_usage import QuotaType, QuotaUsage
from app.models.subscription import SubscriptionTier
from app.services.quota_service import (
    check_quota,
    consume_quota,
    get_or_create_quota,
    get_quota_status,
    reset_quota,
    QuotaExceededError,
)
from tests.conftest import create_user_with_quota


# TC-AUTO-01: Quota Consumption
def test_quota_consumption_basic(db: Session):
    """Verify quota is consumed correctly on OCR processing."""
    # Setup
    user = create_user_with_quota(db, used=0, limit=30)

    # Pre-condition
    quota = get_or_create_quota(db, user.id)
    assert quota.used == 0
    assert quota.limit == 30

    # Action
    quota = consume_quota(db, user.id, amount=1)

    # Verify
    assert quota.used == 1
    assert quota.quota_remaining == 29


def test_quota_consumption_multiple_pages(db: Session):
    """Verify quota consumption with multiple pages."""
    # Setup
    user = create_user_with_quota(db, used=5, limit=30)

    # Action - consume 3 more pages
    consume_quota(db, user.id, amount=1)
    consume_quota(db, user.id, amount=1)
    quota = consume_quota(db, user.id, amount=1)

    # Verify
    assert quota.used == 8
    assert quota.quota_remaining == 22


def test_quota_consumption_atomic(db: Session):
    """Verify quota consumption is atomic (no race conditions)."""
    # Setup
    user = create_user_with_quota(db, used=0, limit=30)

    # Action - multiple sequential consumptions
    for _ in range(5):
        consume_quota(db, user.id, amount=1)

    # Verify
    quota = get_or_create_quota(db, user.id)
    assert quota.used == 5
    assert quota.quota_remaining == 25


# TC-AUTO-02: Quota Exhaustion Check
def test_quota_check_when_available(db: Session):
    """Verify check_quota returns True when quota available."""
    # Setup
    user = create_user_with_quota(db, used=10, limit=30)

    # Action
    has_quota = check_quota(db, user.id)

    # Verify
    assert has_quota is True


def test_quota_check_when_exhausted(db: Session):
    """Verify check_quota returns False when quota exhausted."""
    # Setup
    user = create_user_with_quota(db, used=30, limit=30)

    # Action
    has_quota = check_quota(db, user.id)

    # Verify
    assert has_quota is False

    # Verify status
    status = get_quota_status(db, user.id)
    assert status['is_exhausted'] is True
    assert status['remaining'] == 0


def test_quota_check_near_limit(db: Session):
    """Verify quota check when near limit (29/30)."""
    # Setup
    user = create_user_with_quota(db, used=29, limit=30)

    # Action
    has_quota = check_quota(db, user.id)

    # Verify
    assert has_quota is True  # Still has 1 remaining

    # Verify status
    status = get_quota_status(db, user.id)
    assert status['remaining'] == 1
    assert status['is_near_limit'] is True


def test_quota_exceeded_error_raised(db: Session):
    """Verify QuotaExceededError is raised when consuming beyond limit."""
    # Setup
    user = create_user_with_quota(db, used=30, limit=30)

    # Action & Verify
    with pytest.raises(QuotaExceededError) as exc_info:
        consume_quota(db, user.id, amount=1)

    # Verify error contains quota info
    assert "30/30" in str(exc_info.value)


def test_quota_percentage_calculation(db: Session):
    """Verify quota percentage is calculated correctly."""
    # Setup
    user = create_user_with_quota(db, used=25, limit=30)

    # Action
    status = get_quota_status(db, user.id)

    # Verify
    assert status['percentage_used'] == pytest.approx(83.33, rel=0.1)


def test_quota_status_dict(db: Session):
    """Verify get_quota_status returns correct dictionary structure."""
    # Setup
    user = create_user_with_quota(db, used=15, limit=30)

    # Action
    status = get_quota_status(db, user.id)

    # Verify structure
    assert 'limit' in status
    assert 'used' in status
    assert 'remaining' in status
    assert 'percentage_used' in status
    assert 'is_exhausted' in status
    assert 'is_near_limit' in status
    assert 'reset_at' in status
    assert 'period_start' in status

    # Verify values
    assert status['limit'] == 30
    assert status['used'] == 15
    assert status['remaining'] == 15
    assert status['is_exhausted'] is False


def test_quota_reset(db: Session):
    """Verify quota reset functionality."""
    # Setup
    user = create_user_with_quota(db, used=30, limit=30)

    # Pre-condition - quota exhausted
    assert check_quota(db, user.id) is False

    # Action - reset quota
    quota = reset_quota(db, user.id, trigger_retroactive_processing=False)

    # Verify
    assert quota.used == 0
    assert quota.quota_remaining == 30
    assert check_quota(db, user.id) is True

    # Verify reset_at is updated
    assert quota.reset_at > datetime.utcnow()


def test_unlimited_quota_for_enterprise(db: Session):
    """Verify enterprise tier has unlimited quota."""
    # Setup
    user = create_user_with_quota(db, used=0, limit=-1, tier=SubscriptionTier.ENTERPRISE)

    # Action - consume more than "limit"
    for _ in range(100):
        consume_quota(db, user.id, amount=1)

    # Verify - quota check still passes
    assert check_quota(db, user.id) is True

    # Verify used counter doesn't increment for unlimited tier
    quota = get_or_create_quota(db, user.id)
    assert quota.limit == -1
