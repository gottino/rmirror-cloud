"""NotebookPage model for the mapping between notebooks and pages."""

from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer
from sqlalchemy.orm import relationship

from app.database import Base


class NotebookPage(Base):
    """Mapping table between notebooks and pages.

    This is the source of truth for which pages belong to which notebook
    and in what order. Built from .content files uploaded by the sync agent.
    """

    __tablename__ = "notebook_pages"

    id = Column(Integer, primary_key=True, index=True)
    notebook_id = Column(Integer, ForeignKey("notebooks.id", ondelete="CASCADE"), nullable=False)
    page_id = Column(Integer, ForeignKey("pages.id", ondelete="CASCADE"), nullable=False)
    page_number = Column(Integer, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    notebook = relationship("Notebook", back_populates="notebook_pages")
    page = relationship("Page", back_populates="notebook_pages")

    # Unique constraints defined in migration:
    # - uq_notebook_page: (notebook_id, page_id)
    # - uq_notebook_page_number: (notebook_id, page_number)

    def __repr__(self):
        return f"<NotebookPage(notebook_id={self.notebook_id}, page_id={self.page_id}, page_number={self.page_number})>"
