"""Deleted notebook tombstone model for tracking server-side deletions."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class DeletedNotebook(Base):
    """Tombstone record for notebooks deleted from the server.

    When a user deletes a notebook via the dashboard, a tombstone is created
    so the agent can discover the deletion and exclude the notebook from
    future syncs. The agent acknowledges the tombstone after showing the
    user a warning, at which point the tombstone is removed.
    """

    __tablename__ = "deleted_notebooks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    notebook_uuid: Mapped[str] = mapped_column(String(255), nullable=False)
    visible_name: Mapped[str] = mapped_column(String(500), nullable=False)
    deleted_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    # Relationships
    user: Mapped["User"] = relationship("User")

    __table_args__ = (
        UniqueConstraint("user_id", "notebook_uuid", name="uq_deleted_notebook_user_uuid"),
    )

    def __repr__(self) -> str:
        return f"<DeletedNotebook(user_id={self.user_id}, uuid={self.notebook_uuid})>"
