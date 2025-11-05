"""Highlight model for extracted annotations from PDFs/EPUBs."""

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Highlight(Base):
    """Extracted highlights and annotations from documents."""

    __tablename__ = "highlights"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    notebook_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("notebooks.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Page reference (optional)
    page_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("pages.id", ondelete="SET NULL"), nullable=True
    )
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Text content
    original_text: Mapped[str] = mapped_column(Text, nullable=False)
    corrected_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Source tracking
    source_type: Mapped[str] = mapped_column(String(20), nullable=False)  # pdf, epub, rm
    extraction_method: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Quality metrics
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    match_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Position data (stored as JSON)
    position_data: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Content hash for deduplication
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
    highlighted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="highlights")
    notebook: Mapped["Notebook"] = relationship("Notebook", back_populates="highlights")
    sync_records: Mapped[list["SyncRecord"]] = relationship(
        "SyncRecord",
        back_populates="highlight",
        cascade="all, delete-orphan",
        foreign_keys="SyncRecord.item_id",
        primaryjoin="and_(Highlight.id==SyncRecord.item_id, SyncRecord.item_type=='highlight')",
    )

    def __repr__(self) -> str:
        preview = self.original_text[:50] if self.original_text else ""
        return f"<Highlight(id={self.id}, text='{preview}...')>"
