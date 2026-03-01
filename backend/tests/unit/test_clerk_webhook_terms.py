"""Tests for terms acceptance on user creation via Clerk webhook."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from app.api.webhooks.clerk import handle_user_created
from app.api.users import CURRENT_TOS_VERSION, CURRENT_PRIVACY_VERSION
from app.models.user import User


@pytest.mark.asyncio
async def test_new_user_has_terms_accepted(db: Session):
    """New users created via Clerk webhook should have terms pre-accepted."""
    data = {
        "id": "clerk_test_terms_123",
        "email_addresses": [
            {"email_address": "newuser@example.com", "id": "email_1"}
        ],
        "primary_email_address_id": "email_1",
        "first_name": "Test",
        "last_name": "User",
    }

    mock_settings = MagicMock()
    mock_settings.beta_signup_enabled = False

    with patch("app.api.webhooks.clerk.get_settings", return_value=mock_settings), \
         patch("app.api.webhooks.clerk.track_event"), \
         patch("app.api.webhooks.clerk.get_email_service") as mock_email:
        mock_email.return_value.send_welcome_email.return_value = None
        await handle_user_created(data, db)

    user = db.query(User).filter(User.clerk_user_id == "clerk_test_terms_123").first()
    assert user is not None
    assert user.tos_version == CURRENT_TOS_VERSION
    assert user.privacy_version == CURRENT_PRIVACY_VERSION
    assert user.tos_accepted_at is not None
    assert user.privacy_accepted_at is not None


@pytest.mark.asyncio
async def test_new_user_terms_timestamps_are_recent(db: Session):
    """Terms acceptance timestamps should be set to creation time."""
    before = datetime.utcnow()

    data = {
        "id": "clerk_test_terms_456",
        "email_addresses": [
            {"email_address": "newuser2@example.com", "id": "email_2"}
        ],
        "primary_email_address_id": "email_2",
        "first_name": "Another",
        "last_name": "User",
    }

    mock_settings = MagicMock()
    mock_settings.beta_signup_enabled = False

    with patch("app.api.webhooks.clerk.get_settings", return_value=mock_settings), \
         patch("app.api.webhooks.clerk.track_event"), \
         patch("app.api.webhooks.clerk.get_email_service") as mock_email:
        mock_email.return_value.send_welcome_email.return_value = None
        await handle_user_created(data, db)

    user = db.query(User).filter(User.clerk_user_id == "clerk_test_terms_456").first()
    assert user.tos_accepted_at >= before
    assert user.privacy_accepted_at >= before
