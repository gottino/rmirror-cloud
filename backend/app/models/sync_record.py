"""Sync record models for tracking synchronization to external services."""

from datetime import datetime
from enum import Enum

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SyncStatus(str, Enum):
    """Status of a sync operation."""

    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    RETRY = "retry"


class SyncItemType(str, Enum):
    """Type of item being synced."""

    NOTEBOOK = "notebook"
    PAGE_TEXT = "page_text"
    TODO = "todo"
    HIGHLIGHT = "highlight"


class SyncRecord(Base):
    """
    Unified sync records for all targets (Notion, Readwise, etc.).

    Tracks sync operations using content-hash based deduplication.
    """

    __tablename__ = "sync_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Content tracking
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    target_name: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # "notion", "readwise", etc.
    external_id: Mapped[str] = mapped_column(String(500), nullable=False)  # ID in external system

    # Item details
    item_type: Mapped[str] = mapped_column(String(50), nullable=False)  # SyncItemType value
    item_id: Mapped[str | None] = mapped_column(String(500), nullable=True, index=True)  # Local ID

    # Sync status
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)  # SyncStatus value
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Metadata
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
    synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        Index('idx_sync_content_target', 'content_hash', 'target_name', 'user_id', unique=True),
        Index('idx_sync_content_target_item', 'content_hash', 'target_name', 'item_id'),
    )

    def __repr__(self) -> str:
        return f"<SyncRecord(id={self.id}, target={self.target_name}, status={self.status})>"


class PageSyncRecord(Base):
    """
    Per-page sync records for granular notebook updates.

    Tracks individual page synchronization to support incremental updates.
    """

    __tablename__ = "page_sync_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Page identification
    notebook_uuid: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # Target tracking
    target_name: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    # External IDs (target-specific)
    notion_page_id: Mapped[str | None] = mapped_column(String(500), nullable=True, index=True)
    notion_block_id: Mapped[str | None] = mapped_column(String(500), nullable=True, index=True)

    # Sync status
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
    synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        Index('idx_page_sync_notebook_page_target', 'notebook_uuid', 'page_number', 'target_name', 'user_id', unique=True),
    )

    def __repr__(self) -> str:
        return f"<PageSyncRecord(id={self.id}, notebook={self.notebook_uuid}, page={self.page_number})>"


class IntegrationConfig(Base):
    """
    User integration configurations for external services.

    Stores API keys and settings for Notion, Readwise, etc.
    """

    __tablename__ = "integration_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Integration details
    target_name: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Configuration (stored as JSON)
    config_json: Mapped[str] = mapped_column(Text, nullable=False)  # API keys, database IDs, etc.

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        Index('idx_integration_user_target', 'user_id', 'target_name', unique=True),
    )

    def __repr__(self) -> str:
        return f"<IntegrationConfig(id={self.id}, user={self.user_id}, target={self.target_name})>"
