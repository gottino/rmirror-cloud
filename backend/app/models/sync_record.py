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
    NOTEBOOK_METADATA = "notebook_metadata"  # Lightweight metadata-only sync
    PAGE_TEXT = "page_text"
    TODO = "todo"
    HIGHLIGHT = "highlight"


class SyncRecord(Base):
    """
    Unified sync records for all targets (Notion, Readwise, etc.).

    Tracks sync operations using content-hash based deduplication.
    Consolidates page-level and item-level sync tracking in one table.
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

    # Page tracking (from consolidated page_sync_records)
    page_uuid: Mapped[str | None] = mapped_column(String(255), nullable=True)  # reMarkable page UUID
    notebook_uuid: Mapped[str | None] = mapped_column(String(255), nullable=True)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)

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
        Index('idx_sync_content_target', 'content_hash', 'target_name', 'user_id'),
        Index('idx_sync_content_target_item', 'content_hash', 'target_name', 'item_id'),
        Index('idx_sync_page_uuid', 'page_uuid', 'target_name', 'user_id', unique=True),
        Index('idx_sync_notebook_page', 'notebook_uuid', 'page_number'),
    )

    def __repr__(self) -> str:
        return f"<SyncRecord(id={self.id}, target={self.target_name}, status={self.status})>"


class SyncQueue(Base):
    """
    Background sync queue for processing sync operations asynchronously.

    Items are added to this queue on OCR completion or when catch-up sync is needed.
    """

    __tablename__ = "sync_queue"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Item to sync
    item_type: Mapped[str] = mapped_column(String(50), nullable=False)  # 'page_text', 'todo', 'highlight'
    item_id: Mapped[str] = mapped_column(String(255), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    # Context
    page_uuid: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notebook_uuid: Mapped[str | None] = mapped_column(String(255), nullable=True)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Target
    target_name: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    # Queue status
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True, default="pending")
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=5)  # 1-10, lower = higher priority
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)  # For retry backoff
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        Index('idx_queue_user', 'user_id'),
        Index('idx_queue_status', 'status'),
        Index('idx_queue_target', 'target_name'),
        Index('idx_queue_scheduled', 'scheduled_at'),
        Index('idx_queue_priority_status', 'priority', 'status', 'scheduled_at'),
        Index('idx_queue_dedup', 'content_hash', 'target_name', 'user_id', 'status'),
    )

    def __repr__(self) -> str:
        return f"<SyncQueue(id={self.id}, item_type={self.item_type}, target={self.target_name}, status={self.status})>"


class IntegrationConfig(Base):
    """
    User integration configurations for external services.

    Stores encrypted API keys and settings for Notion, Readwise, etc.
    Credentials are encrypted at rest using Fernet (symmetric encryption).
    """

    __tablename__ = "integration_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Integration details
    target_name: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Configuration (encrypted JSON containing API keys, database IDs, etc.)
    config_encrypted: Mapped[str] = mapped_column(Text, nullable=False)

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

    def set_config(self, config_dict: dict) -> None:
        """
        Encrypt and store configuration.

        Args:
            config_dict: Configuration data (API keys, tokens, etc.)

        Example:
            >>> integration.set_config({"notion_token": "secret_xyz", "database_id": "abc123"})
        """
        from app.services.encryption import get_encryption_service

        encryption_service = get_encryption_service()
        self.config_encrypted = encryption_service.encrypt_config(config_dict, self.user_id)
        self.updated_at = datetime.utcnow()

    def get_config(self) -> dict:
        """
        Decrypt and return configuration.

        Returns:
            Decrypted configuration dictionary

        Raises:
            cryptography.fernet.InvalidToken: If decryption fails

        Example:
            >>> config = integration.get_config()
            >>> notion_token = config["notion_token"]
        """
        from app.services.encryption import get_encryption_service

        encryption_service = get_encryption_service()
        return encryption_service.decrypt_config(self.config_encrypted, self.user_id)

    def __repr__(self) -> str:
        return f"<IntegrationConfig(id={self.id}, user={self.user_id}, target={self.target_name})>"
