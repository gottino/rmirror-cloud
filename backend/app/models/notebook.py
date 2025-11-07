"""Notebook model for reMarkable documents."""

from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class DocumentType(str, Enum):
    """Document type options."""

    PDF = "pdf"
    EPUB = "epub"
    NOTEBOOK = "notebook"
    FOLDER = "folder"


class Notebook(Base):
    """reMarkable notebooks and documents."""

    __tablename__ = "notebooks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # reMarkable metadata
    notebook_uuid: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    visible_name: Mapped[str] = mapped_column(String(500), nullable=False)
    document_type: Mapped[str] = mapped_column(String(20), nullable=False)

    # Folder hierarchy
    parent_uuid: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    full_path: Mapped[str | None] = mapped_column(String(2000), nullable=True)

    # Document metadata
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    author: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Storage
    s3_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    file_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Metadata
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="notebooks")
    pages: Mapped[list["Page"]] = relationship(
        "Page", back_populates="notebook", cascade="all, delete-orphan"
    )
    highlights: Mapped[list["Highlight"]] = relationship(
        "Highlight", back_populates="notebook", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Notebook(id={self.id}, name={self.visible_name})>"
