"""Waitlist API endpoints with beta invite system."""

import base64
import hashlib
import hmac
import json
import logging
import time
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy import Column, DateTime, Integer, String, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.clerk import get_clerk_active_user
from app.config import get_settings
from app.database import Base, get_db
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/waitlist", tags=["waitlist"])


# ==================== Model ====================


class WaitlistEntry(Base):
    """Waitlist database model."""

    __tablename__ = "waitlist"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    name = Column(String(255), nullable=True)
    status = Column(String(20), default="pending", nullable=False)
    invite_token = Column(String(512), nullable=True, unique=True)
    approved_at = Column(DateTime, nullable=True)
    claimed_at = Column(DateTime, nullable=True)
    claimed_by = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


# ==================== Schemas ====================


class WaitlistCreate(BaseModel):
    """Waitlist creation schema."""

    email: EmailStr
    name: Optional[str] = None


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


def _create_invite_token(email: str, waitlist_id: int, secret_key: str) -> str:
    """Create an HMAC-signed invite token encoding email and expiration."""
    settings = get_settings()
    expiry_seconds = settings.invite_token_expiry_days * 86400
    payload = json.dumps({
        "email": email,
        "wid": waitlist_id,
        "exp": int(time.time()) + expiry_seconds,
    })
    payload_b64 = base64.urlsafe_b64encode(payload.encode()).decode()
    signature = hmac.new(
        secret_key.encode(), payload_b64.encode(), hashlib.sha256
    ).hexdigest()
    return f"{payload_b64}.{signature}"


def _validate_invite_token(token: str, secret_key: str) -> Optional[dict]:
    """Validate an HMAC-signed invite token. Returns payload dict or None."""
    try:
        parts = token.split(".")
        if len(parts) != 2:
            return None
        payload_b64, signature = parts
        expected_sig = hmac.new(
            secret_key.encode(), payload_b64.encode(), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(signature, expected_sig):
            return None
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        if payload.get("exp", 0) < int(time.time()):
            return None
        return payload
    except Exception:
        return None


# ==================== Admin Auth ====================


async def get_admin_user(
    current_user: User = Depends(get_clerk_active_user),
) -> User:
    """Verify the current user is an admin."""
    settings = get_settings()
    admin_ids = [x.strip() for x in settings.admin_user_ids.split(",") if x.strip()]
    if current_user.clerk_user_id not in admin_ids:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


# ==================== Public Endpoints ====================


@router.post("", response_model=WaitlistResponse, status_code=201)
async def join_waitlist(
    data: WaitlistCreate,
    db: Session = Depends(get_db),
) -> WaitlistEntry:
    """Add an email to the waitlist."""
    # Check if email already exists
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
            db.refresh(existing)
        return existing

    # Create new entry
    entry = WaitlistEntry(email=data.email, name=data.name)
    db.add(entry)

    try:
        db.commit()
        db.refresh(entry)
        return entry
    except IntegrityError:
        db.rollback()
        existing = (
            db.query(WaitlistEntry)
            .filter(WaitlistEntry.email == data.email)
            .first()
        )
        if existing:
            return existing
        raise HTTPException(status_code=500, detail="Failed to add email to waitlist")


@router.get("/validate-invite", response_model=InviteValidationResponse)
async def validate_invite(
    token: str,
    db: Session = Depends(get_db),
):
    """Validate an invite token (public endpoint)."""
    settings = get_settings()

    if not token:
        return InviteValidationResponse(valid=False, reason="No token provided")

    payload = _validate_invite_token(token, settings.secret_key)
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
    token = _create_invite_token(entry.email, entry.id, settings.secret_key)
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

        token = _create_invite_token(entry.email, entry.id, settings.secret_key)
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
