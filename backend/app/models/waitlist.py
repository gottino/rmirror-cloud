"""Waitlist entry model."""

from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String

from app.database import Base


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
