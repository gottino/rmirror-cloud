"""Page model for individual document pages with OCR tracking."""

from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class OcrStatus(str, Enum):
    """OCR processing status."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class Page(Base):
    """Individual pages within notebooks, with OCR tracking."""

    __tablename__ = "pages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    notebook_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("notebooks.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Page identification
    page_uuid: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Storage
    s3_key: Mapped[str | None] = mapped_column(String(500), nullable=True)  # .rm file
    pdf_s3_key: Mapped[str | None] = mapped_column(String(500), nullable=True)  # PDF version
    file_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    # OCR
    ocr_status: Mapped[str] = mapped_column(
        String(20), default=OcrStatus.PENDING, nullable=False, index=True
    )
    ocr_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    ocr_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
    ocr_completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Relationships
    notebook: Mapped["Notebook"] = relationship("Notebook", back_populates="pages")
    notebook_pages: Mapped[list["NotebookPage"]] = relationship(
        "NotebookPage", back_populates="page", cascade="all, delete-orphan"
    )
    todos: Mapped[list["Todo"]] = relationship(
        "Todo", back_populates="page", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Page(id={self.id}, notebook_id={self.notebook_id}, uuid={self.page_uuid})>"
