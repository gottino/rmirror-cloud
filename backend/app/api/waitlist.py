"""Waitlist API endpoints."""

from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy import Column, DateTime, Integer, String
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import Base, get_db

router = APIRouter(prefix="/waitlist", tags=["waitlist"])


class WaitlistEntry(Base):
    """Waitlist database model."""

    __tablename__ = "waitlist"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class WaitlistCreate(BaseModel):
    """Waitlist creation schema."""

    email: EmailStr


class WaitlistResponse(BaseModel):
    """Waitlist response schema."""

    email: str
    created_at: datetime

    class Config:
        from_attributes = True


@router.post("", response_model=WaitlistResponse, status_code=201)
async def join_waitlist(
    data: WaitlistCreate,
    db: AsyncSession = Depends(get_db),
) -> WaitlistEntry:
    """Add an email to the waitlist."""
    from sqlalchemy import select
    from sqlalchemy.exc import IntegrityError

    # Check if email already exists
    result = await db.execute(
        select(WaitlistEntry).where(WaitlistEntry.email == data.email)
    )
    existing = result.scalar_one_or_none()

    if existing:
        # Return existing entry (idempotent)
        return existing

    # Create new entry
    entry = WaitlistEntry(email=data.email)
    db.add(entry)

    try:
        await db.commit()
        await db.refresh(entry)
        return entry
    except IntegrityError:
        await db.rollback()
        # Handle race condition - email was added between check and insert
        result = await db.execute(
            select(WaitlistEntry).where(WaitlistEntry.email == data.email)
        )
        existing = result.scalar_one_or_none()
        if existing:
            return existing
        raise HTTPException(status_code=500, detail="Failed to add email to waitlist")


@router.get("", response_model=List[WaitlistResponse])
async def get_waitlist(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
) -> List[WaitlistEntry]:
    """Get all waitlist entries (admin only - add auth later)."""
    from sqlalchemy import select

    result = await db.execute(
        select(WaitlistEntry)
        .order_by(WaitlistEntry.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    return result.scalars().all()
