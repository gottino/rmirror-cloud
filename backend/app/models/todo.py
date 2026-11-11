"""Todo model for extracted tasks from handwritten notes."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

REMOVED_FROM_PAGE = "page"
REMOVED_BY_USER = "user"


class Todo(Base):
    """Extracted todo items/tasks from handwritten notes.

    Includes fuzzy deduplication to prevent creating duplicate todos
    when OCR variations occur on re-processing.
    """

    __tablename__ = "todos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    notebook_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("notebooks.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Page reference
    page_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("pages.id", ondelete="SET NULL"), nullable=True
    )
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_uuid: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)

    # Todo content
    title: Mapped[str] = mapped_column(String(200), nullable=False)  # Shortened version
    text: Mapped[str] = mapped_column(Text, nullable=False)  # Full text
    completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Deduplication fields
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)  # SHA-256 hash
    fuzzy_signature: Mapped[str | None] = mapped_column(String(100), nullable=True)  # Fuzzy matching key

    # Extraction metadata
    source_file: Mapped[str | None] = mapped_column(String(255), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Date extracted from page annotation (e.g., handwritten date on page)
    date_extracted: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Position data (bounding box as JSON)
    bounding_box: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Soft removal. The todo stays in the table (and its task in Todoist or
    # Notion is left alone) so a later extraction of the same page matches it
    # instead of creating it again. Reasons: REMOVED_FROM_PAGE (the line is no
    # longer on the page; undone if it comes back) and REMOVED_BY_USER (deleted
    # in the dashboard; never undone by extraction).
    removed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    removed_reason: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="todos")
    notebook: Mapped["Notebook"] = relationship("Notebook", back_populates="todos")
    page: Mapped["Page"] = relationship("Page", back_populates="todos")

    __table_args__ = (
        Index('idx_todos_fuzzy', 'fuzzy_signature', 'notebook_id', 'user_id', unique=True),
    )

    def __repr__(self) -> str:
        status = "✓" if self.completed else "☐"
        preview = self.text[:50] if self.text else ""
        return f"<Todo(id={self.id}, {status} '{preview}...')>"
