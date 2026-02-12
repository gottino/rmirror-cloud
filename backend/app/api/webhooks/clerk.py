"""Clerk webhook handler for user synchronization."""

import json
import logging
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from svix.webhooks import Webhook, WebhookVerificationError

from app.config import get_settings
from app.database import get_db
from app.models.subscription import Subscription, SubscriptionStatus, SubscriptionTier
from app.models.user import User
from app.utils.email import get_email_service

logger = logging.getLogger(__name__)

router = APIRouter()

# Track if we've warned about missing webhook secret in dev mode
_webhook_secret_warned = False


def verify_webhook_signature(payload: bytes, headers: dict, webhook_secret: str) -> bool:
    """
    Verify that the webhook request came from Clerk using Svix.

    Args:
        payload: Raw request body
        headers: Request headers
        webhook_secret: Clerk webhook signing secret

    Returns:
        True if signature is valid
    """
    try:
        wh = Webhook(webhook_secret)
        # Svix expects headers as dict with lowercase keys
        svix_headers = {
            "svix-id": headers.get("svix-id"),
            "svix-timestamp": headers.get("svix-timestamp"),
            "svix-signature": headers.get("svix-signature"),
        }
        # This will raise WebhookVerificationError if invalid
        wh.verify(payload, svix_headers)
        return True
    except WebhookVerificationError:
        return False
    except Exception as e:
        logger.error(f"Webhook verification error: {e}")
        return False


@router.post("")
async def clerk_webhook(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
):
    """
    Handle Clerk webhook events for user synchronization.

    Supported events:
    - user.created: Create new user in database
    - user.updated: Update existing user
    - user.deleted: Deactivate user

    Args:
        request: FastAPI request object
        db: Database session

    Returns:
        Success response

    Raises:
        HTTPException: If webhook signature is invalid
    """
    settings = get_settings()

    # Get raw body for signature verification
    body = await request.body()
    headers = dict(request.headers)

    # Verify webhook signature
    global _webhook_secret_warned

    if not settings.clerk_webhook_secret:
        # In production, webhook secret is required
        if not settings.debug:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Webhook secret not configured",
            )
        # In development, warn once and allow
        if not _webhook_secret_warned:
            logger.warning(
                "CLERK_WEBHOOK_SECRET not configured - webhook signature verification disabled. "
                "This is a SECURITY RISK. Set CLERK_WEBHOOK_SECRET to your Clerk webhook signing secret."
            )
            _webhook_secret_warned = True
    else:
        # Verify signature
        if not verify_webhook_signature(body, headers, settings.clerk_webhook_secret):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid webhook signature",
            )

    # Parse webhook payload
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload",
        )

    event_type = payload.get("type")
    data = payload.get("data", {})

    print(f"Received Clerk webhook: {event_type}")

    # Handle different event types
    if event_type == "user.created":
        await handle_user_created(data, db)
    elif event_type == "user.updated":
        await handle_user_updated(data, db)
    elif event_type == "user.deleted":
        await handle_user_deleted(data, db)
    else:
        print(f"Unhandled event type: {event_type}")

    return {"success": True}


async def handle_user_created(data: dict, db: Session):
    """
    Handle user.created event from Clerk.

    Args:
        data: User data from Clerk
        db: Database session
    """
    clerk_user_id = data.get("id")
    email_addresses = data.get("email_addresses", [])
    primary_email = next(
        (email["email_address"] for email in email_addresses if email.get("id") == data.get("primary_email_address_id")),
        None,
    )

    if not clerk_user_id or not primary_email:
        print(f"Missing required fields in user.created event: {data}")
        return

    # Check if user already exists
    existing_user = db.query(User).filter(User.clerk_user_id == clerk_user_id).first()
    if existing_user:
        print(f"User with Clerk ID {clerk_user_id} already exists")
        return

    # Extract name from Clerk data
    first_name = data.get("first_name", "")
    last_name = data.get("last_name", "")
    full_name = f"{first_name} {last_name}".strip() or primary_email.split("@")[0]

    # Create new user
    new_user = User(
        email=primary_email,
        full_name=full_name,
        clerk_user_id=clerk_user_id,
        hashed_password=None,  # No password for Clerk users
        is_active=True,
        created_at=datetime.utcnow(),
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    print(f"Created user: {new_user.email} (Clerk ID: {clerk_user_id})")

    # Create free tier subscription for new user
    from datetime import timedelta
    subscription = Subscription(
        user_id=new_user.id,
        tier=SubscriptionTier.FREE,
        status=SubscriptionStatus.ACTIVE,
        current_period_start=datetime.utcnow(),
        current_period_end=datetime.utcnow() + timedelta(days=30),
    )
    db.add(subscription)
    db.commit()
    print(f"Created free tier subscription for user {new_user.id}")

    # Mark waitlist invite as claimed (if exists)
    try:
        from app.api.waitlist import WaitlistEntry

        waitlist_entry = (
            db.query(WaitlistEntry)
            .filter(
                WaitlistEntry.email == primary_email,
                WaitlistEntry.status == "approved",
            )
            .first()
        )
        if waitlist_entry:
            waitlist_entry.status = "claimed"
            waitlist_entry.claimed_at = datetime.utcnow()
            waitlist_entry.claimed_by = clerk_user_id
            db.commit()
            print(f"Marked waitlist invite as claimed for {primary_email}")
    except Exception as e:
        print(f"Error marking waitlist invite as claimed: {str(e)}")
        # Don't fail the webhook if waitlist update fails

    # Send welcome email to new user
    try:
        email_service = get_email_service()
        email_sent = email_service.send_welcome_email(
            user_email=new_user.email,
            user_name=new_user.full_name
        )
        if email_sent:
            print(f"Welcome email sent to {new_user.email}")
        else:
            print(f"Failed to send welcome email to {new_user.email}")
    except Exception as e:
        print(f"Error sending welcome email to {new_user.email}: {str(e)}")
        # Don't fail the webhook if email fails


async def handle_user_updated(data: dict, db: Session):
    """
    Handle user.updated event from Clerk.

    Args:
        data: User data from Clerk
        db: Database session
    """
    clerk_user_id = data.get("id")

    if not clerk_user_id:
        print(f"Missing Clerk user ID in user.updated event: {data}")
        return

    # Find user
    user = db.query(User).filter(User.clerk_user_id == clerk_user_id).first()
    if not user:
        print(f"User with Clerk ID {clerk_user_id} not found")
        # Create user if not exists
        await handle_user_created(data, db)
        return

    # Update user data
    email_addresses = data.get("email_addresses", [])
    primary_email = next(
        (email["email_address"] for email in email_addresses if email.get("id") == data.get("primary_email_address_id")),
        None,
    )

    if primary_email:
        user.email = primary_email

    first_name = data.get("first_name", "")
    last_name = data.get("last_name", "")
    if first_name or last_name:
        user.full_name = f"{first_name} {last_name}".strip()

    db.commit()
    print(f"Updated user: {user.email} (Clerk ID: {clerk_user_id})")


async def handle_user_deleted(data: dict, db: Session):
    """
    Handle user.deleted event from Clerk.

    If the user was already deleted from our DB (via the Settings danger zone),
    this is a follow-up webhook — just log and return.

    If the user still exists (deletion initiated from Clerk dashboard directly),
    perform the full cleanup: S3 files + DB cascade.

    Args:
        data: User data from Clerk
        db: Database session
    """
    clerk_user_id = data.get("id")

    if not clerk_user_id:
        logger.warning(f"Missing Clerk user ID in user.deleted event: {data}")
        return

    # Find user
    user = db.query(User).filter(User.clerk_user_id == clerk_user_id).first()
    if not user:
        # User already deleted from our DB (API-initiated deletion)
        logger.info(
            f"User with Clerk ID {clerk_user_id} not found in DB — "
            "likely already deleted via API. No-op."
        )
        return

    # User exists — deletion was initiated from Clerk dashboard, not our UI.
    # Perform full cleanup.
    logger.info(
        f"Clerk-initiated deletion for user {user.email} (Clerk ID: {clerk_user_id}). "
        "Performing full account cleanup."
    )

    from app.dependencies import get_storage_service
    from app.services.account_service import AccountService

    storage = get_storage_service()
    try:
        summary = await AccountService.delete_account(
            user_id=user.id,
            db=db,
            storage=storage,
            clerk_secret_key=None,  # Don't call Clerk API back — Clerk already deleted the user
        )
        logger.info(
            f"Completed Clerk-initiated deletion for user {user.email}: {summary}"
        )
    except Exception as e:
        logger.error(
            f"Failed Clerk-initiated deletion for user {user.email} "
            f"(Clerk ID: {clerk_user_id}): {e}"
        )
        # Fall back to soft delete so the user is at least deactivated
        try:
            user_check = db.query(User).filter(User.id == user.id).first()
            if user_check:
                user_check.is_active = False
                db.commit()
                logger.info(f"Fell back to soft-delete for user {user.email}")
        except Exception:
            pass
