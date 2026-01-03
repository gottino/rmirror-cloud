"""Quota usage model for tracking user OCR consumption."""

from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class QuotaType(str, Enum):
    """Quota type options."""

    OCR = "ocr"


class QuotaUsage(Base):
    """Track user quota consumption by type and period."""

    __tablename__ = "quota_usage"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Quota details
    quota_type: Mapped[str] = mapped_column(
        String(20), default=QuotaType.OCR, nullable=False
    )
    limit: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Billing period
    reset_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    period_start: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="quota_usages")

    def __repr__(self) -> str:
        return f"<QuotaUsage(id={self.id}, user_id={self.user_id}, type={self.quota_type}, used={self.used}/{self.limit})>"

    @property
    def quota_remaining(self) -> int:
        """Calculate remaining quota."""
        return max(0, self.limit - self.used)

    @property
    def percentage_used(self) -> float:
        """Calculate percentage of quota used."""
        if self.limit == 0:
            return 100.0
        return min(100.0, (self.used / self.limit) * 100)

    @property
    def is_exhausted(self) -> bool:
        """Check if quota is exhausted."""
        return self.used >= self.limit

    @property
    def is_near_limit(self, threshold: float = 0.8) -> bool:
        """Check if quota usage is near the limit (default 80%)."""
        return (self.used / self.limit) >= threshold if self.limit > 0 else False
