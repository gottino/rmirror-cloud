"""Waitlist API endpoints with beta invite system."""

import logging
import time
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import signing
from app.auth.clerk import get_clerk_session_user
from app.config import get_settings
from app.database import get_db
from app.middleware.rate_limit import UNAUTHENTICATED_LIMIT, limiter
from app.models.user import User
from app.models.waitlist import WaitlistEntry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/waitlist", tags=["waitlist"])


# The WaitlistEntry model lives in app.models.waitlist so that migrations and
# the schema check see it; it is imported above for existing callers.


# ==================== Schemas ====================


class WaitlistCreate(BaseModel):
    """Waitlist creation schema."""

    email: EmailStr
    name: Optional[str] = None


class WaitlistJoinResponse(BaseModel):
    """Fixed acknowledgement for public signups (same for new and known emails)."""

    status: str = "ok"
    message: str = "Thanks! You are on the waitlist."


class WaitlistResponse(BaseModel):
    """Waitlist response schema."""

    id: int
    email: str
    name: Optional[str] = None
    status: str
    created_at: datetime
    approved_at: Optional[datetime] = None
    claimed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class WaitlistAdminResponse(BaseModel):
    """Admin response with stats."""

    entries: List[WaitlistResponse]
    total: int
    stats: dict


class BulkApproveRequest(BaseModel):
    """Request to approve multiple waitlist entries."""

    ids: List[int]


class InviteValidationResponse(BaseModel):
    """Response from invite token validation."""

    valid: bool
    email: Optional[str] = None
    reason: Optional[str] = None


# ==================== HMAC Invite Tokens ====================


def _create_invite_token(email: str, waitlist_id: int) -> str:
    """Create an HMAC-signed invite token encoding email and expiration."""
    settings = get_settings()
    expiry_seconds = settings.invite_token_expiry_days * 86400
    payload = {
        "email": email,
        "wid": waitlist_id,
        "exp": int(time.time()) + expiry_seconds,
    }
    return signing.sign(payload, signing.derive_key(signing.INVITE_TOKEN_PURPOSE))


def _validate_invite_token(token: str) -> Optional[dict]:
    """Validate an HMAC-signed invite token. Returns payload dict or None."""
    keys = [
        signing.derive_key(signing.INVITE_TOKEN_PURPOSE),
        # Legacy: invites sent before per-purpose keys were signed with the raw
        # SECRET_KEY and stay valid for invite_token_expiry_days. This branch
        # can be removed after 2026-12-31.
        get_settings().secret_key.encode(),
    ]
    return signing.verify(token, keys)


# ==================== Admin Auth ====================


async def get_admin_user(
    current_user: User = Depends(get_clerk_session_user),
) -> User:
    """Verify the current user is an admin."""
    settings = get_settings()
    admin_ids = [x.strip() for x in settings.admin_user_ids.split(",") if x.strip()]
    if current_user.clerk_user_id not in admin_ids:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


# ==================== Public Endpoints ====================


def _notify_admin_of_signup(email: str, name: Optional[str]) -> None:
    """Send the admin signup notification. Never raises.

    Plain ``def`` on purpose: the Resend SDK call is blocking, and Starlette
    runs sync background functions in a threadpool, off the event loop.
    """
    settings = get_settings()
    if not settings.admin_email:
        logger.info("ADMIN_EMAIL not set; skipping waitlist admin notification")
        return
    try:
        from app.utils.email import get_email_service

        get_email_service().send_waitlist_notification_email(email=email, name=name)
    except Exception as e:
        logger.error(f"Failed to send waitlist notification: {e}")


@router.post("", response_model=WaitlistJoinResponse, status_code=202)
@limiter.limit(UNAUTHENTICATED_LIMIT)  # public: per IP
async def join_waitlist(
    request: Request,
    data: WaitlistCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> WaitlistJoinResponse:
    """Add an email to the waitlist.

    The response is identical whether or not the address was already on the
    list, so the endpoint does not reveal who has signed up.
    """
    ack = WaitlistJoinResponse()

    existing = (
        db.query(WaitlistEntry)
        .filter(WaitlistEntry.email == data.email)
        .first()
    )

    if existing:
        # Update name if provided and not already set
        if data.name and not existing.name:
            existing.name = data.name
            db.commit()
        return ack

    entry = WaitlistEntry(email=data.email, name=data.name)
    db.add(entry)

    try:
        db.commit()
    except IntegrityError:
        # Concurrent signup of the same address: treat as already on the list
        db.rollback()
        return ack

    background_tasks.add_task(_notify_admin_of_signup, data.email, data.name)
    return ack


@router.get("/validate-invite", response_model=InviteValidationResponse)
@limiter.limit(UNAUTHENTICATED_LIMIT)  # public: per IP
async def validate_invite(
    request: Request,
    token: str,
    db: Session = Depends(get_db),
):
    """Validate an invite token (public endpoint)."""
    if not token:
        return InviteValidationResponse(valid=False, reason="No token provided")

    payload = _validate_invite_token(token)
    if not payload:
        return InviteValidationResponse(
            valid=False, reason="Invalid or expired invite link"
        )

    # Check if the invite has already been claimed
    entry = (
        db.query(WaitlistEntry)
        .filter(
            WaitlistEntry.id == payload.get("wid"),
            WaitlistEntry.email == payload.get("email"),
        )
        .first()
    )

    if not entry:
        return InviteValidationResponse(
            valid=False, reason="Invite not found"
        )

    if entry.status == "claimed":
        return InviteValidationResponse(
            valid=False, reason="This invite has already been used"
        )

    if entry.status != "approved":
        return InviteValidationResponse(
            valid=False, reason="Invite is not valid"
        )

    return InviteValidationResponse(valid=True, email=entry.email)


# ==================== Admin Endpoints ====================


@router.get("/admin", response_model=WaitlistAdminResponse)
async def get_waitlist_admin(
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """List waitlist entries with optional status filter (admin only)."""
    query = db.query(WaitlistEntry)
    if status:
        query = query.filter(WaitlistEntry.status == status)
    entries = (
        query.order_by(WaitlistEntry.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    # Get total count with filter
    count_query = db.query(func.count(WaitlistEntry.id))
    if status:
        count_query = count_query.filter(WaitlistEntry.status == status)
    total = count_query.scalar()

    # Get stats
    stats_rows = (
        db.query(WaitlistEntry.status, func.count(WaitlistEntry.id))
        .group_by(WaitlistEntry.status)
        .all()
    )
    stats = {row[0]: row[1] for row in stats_rows}

    return WaitlistAdminResponse(
        entries=entries,
        total=total,
        stats={
            "pending": stats.get("pending", 0),
            "approved": stats.get("approved", 0),
            "claimed": stats.get("claimed", 0),
        },
    )


@router.post("/admin/{entry_id}/approve", response_model=WaitlistResponse)
async def approve_waitlist_entry(
    entry_id: int,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """Approve a single waitlist entry and send invite email (admin only)."""
    entry = (
        db.query(WaitlistEntry)
        .filter(WaitlistEntry.id == entry_id)
        .first()
    )

    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")

    if entry.status != "pending":
        raise HTTPException(
            status_code=400, detail=f"Entry is already {entry.status}"
        )

    settings = get_settings()

    # Generate invite token
    token = _create_invite_token(entry.email, entry.id)
    entry.status = "approved"
    entry.invite_token = token
    entry.approved_at = datetime.utcnow()

    db.commit()
    db.refresh(entry)

    # Send invite email
    try:
        from app.utils.email import get_email_service

        email_service = get_email_service()
        invite_link = f"{settings.dashboard_url}/sign-up?invite={token}"
        email_service.send_invite_approved_email(
            email=entry.email,
            name=entry.name,
            invite_link=invite_link,
        )
        logger.info(f"Invite email sent to {entry.email}")
    except Exception as e:
        logger.error(f"Failed to send invite email to {entry.email}: {e}")
        # Don't fail the approval if email fails

    return entry


@router.post("/admin/approve-bulk")
async def approve_waitlist_bulk(
    data: BulkApproveRequest,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """Approve multiple waitlist entries (admin only)."""
    settings = get_settings()
    approved = []
    errors = []

    for entry_id in data.ids:
        entry = (
            db.query(WaitlistEntry)
            .filter(WaitlistEntry.id == entry_id)
            .first()
        )

        if not entry:
            errors.append({"id": entry_id, "error": "Not found"})
            continue

        if entry.status != "pending":
            errors.append({"id": entry_id, "error": f"Already {entry.status}"})
            continue

        token = _create_invite_token(entry.email, entry.id)
        entry.status = "approved"
        entry.invite_token = token
        entry.approved_at = datetime.utcnow()
        approved.append(entry)

    db.commit()

    # Send invite emails
    from app.utils.email import get_email_service

    email_service = get_email_service()
    for entry in approved:
        try:
            invite_link = f"{settings.dashboard_url}/sign-up?invite={entry.invite_token}"
            email_service.send_invite_approved_email(
                email=entry.email,
                name=entry.name,
                invite_link=invite_link,
            )
        except Exception as e:
            logger.error(f"Failed to send invite email to {entry.email}: {e}")

    return {
        "approved": len(approved),
        "errors": errors,
    }
