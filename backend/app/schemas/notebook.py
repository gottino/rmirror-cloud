"""Notebook schemas."""

from datetime import datetime

from pydantic import BaseModel

from app.schemas.page import Page


class NotebookBase(BaseModel):
    """Base notebook schema."""

    visible_name: str
    document_type: str
    title: str | None = None
    author: str | None = None


class Notebook(NotebookBase):
    """Notebook response schema."""

    id: int
    notebook_uuid: str
    user_id: int
    s3_key: str | None = None
    file_hash: str | None = None
    file_size: int | None = None
    created_at: datetime
    updated_at: datetime
    last_synced_at: datetime | None = None

    class Config:
        from_attributes = True


class NotebookPageCounts(BaseModel):
    """Page counts for a notebook, by sync/OCR state."""

    total_pages: int
    synced_pages: int
    not_synced_pages: int
    pending_quota_pages: int


class NotebookWithPages(Notebook):
    """Notebook response schema with pages.

    ``pages`` is empty when the request asked for ``include_pages=false``;
    ``page_counts`` is always filled so clients can show totals without
    loading every page.
    """

    pages: list[Page] = []
    page_counts: NotebookPageCounts | None = None

    class Config:
        from_attributes = True


class NotebookPagesResponse(BaseModel):
    """One window of a notebook's pages, in notebook page order."""

    items: list[Page]
    total: int
    offset: int
    limit: int
    has_more: bool


class NotebookUploadResponse(BaseModel):
    """Response after file upload."""

    notebook: Notebook
    message: str
