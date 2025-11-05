"""Processing job model for async task queue."""

from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class JobStatus(str, Enum):
    """Job processing status."""

    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobType(str, Enum):
    """Job type options."""

    EXTRACT_HIGHLIGHTS = "extract_highlights"
    OCR_PAGE = "ocr_page"
    SYNC_TO_SERVICE = "sync_to_service"
    PROCESS_NOTEBOOK = "process_notebook"


class ProcessingJob(Base):
    """Async processing jobs tracked in database."""

    __tablename__ = "processing_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Job details
    job_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    job_status: Mapped[str] = mapped_column(
        String(20), default=JobStatus.QUEUED, nullable=False, index=True
    )

    # Job data (JSON)
    input_data: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_data: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Queue management
    queue_name: Mapped[str] = mapped_column(String(50), default="default", nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_retries: Mapped[int] = mapped_column(Integer, default=3, nullable=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="processing_jobs")

    def __repr__(self) -> str:
        return (
            f"<ProcessingJob(id={self.id}, type={self.job_type}, status={self.job_status})>"
        )
