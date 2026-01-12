"""Clerk webhook handler for user synchronization."""

import json
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from svix.webhooks import Webhook, WebhookVerificationError

from app.config import get_settings
from app.database import get_db
from app.models.user import User
from app.models.subscription import Subscription, SubscriptionTier, SubscriptionStatus
from app.utils.email import get_email_service

router = APIRouter()


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
        print(f"Webhook verification error: {e}")
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

    # Verify webhook signature if secret is configured
    if settings.clerk_webhook_secret:
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

    Args:
        data: User data from Clerk
        db: Database session
    """
    clerk_user_id = data.get("id")

    if not clerk_user_id:
        print(f"Missing Clerk user ID in user.deleted event: {data}")
        return

    # Find user
    user = db.query(User).filter(User.clerk_user_id == clerk_user_id).first()
    if not user:
        print(f"User with Clerk ID {clerk_user_id} not found")
        return

    # Deactivate user instead of deleting
    user.is_active = False
    db.commit()
    print(f"Deactivated user: {user.email} (Clerk ID: {clerk_user_id})")
