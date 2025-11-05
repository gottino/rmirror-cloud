"""Sync record model for tracking external service synchronization."""

from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class SyncStatus(str, Enum):
    """Sync status options."""

    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class SyncRecord(Base):
    """Tracks synchronization of items to external services."""

    __tablename__ = "sync_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # Item reference (polymorphic)
    item_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    item_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    # Target service
    target_service: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Sync tracking
    sync_status: Mapped[str] = mapped_column(
        String(20), default=SyncStatus.PENDING, nullable=False, index=True
    )
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Relationships (for highlights)
    highlight: Mapped["Highlight | None"] = relationship(
        "Highlight",
        back_populates="sync_records",
        foreign_keys=[item_id],
        primaryjoin="and_(SyncRecord.item_id==Highlight.id, SyncRecord.item_type=='highlight')",
        viewonly=True,
    )

    def __repr__(self) -> str:
        return (
            f"<SyncRecord(id={self.id}, service={self.target_service}, "
            f"status={self.sync_status})>"
        )
