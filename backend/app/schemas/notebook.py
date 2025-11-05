"""Notebook schemas."""

from datetime import datetime

from pydantic import BaseModel


class NotebookBase(BaseModel):
    """Base notebook schema."""

    visible_name: str
    document_type: str
    title: str | None = None
    author: str | None = None


class NotebookCreate(NotebookBase):
    """Notebook creation schema."""

    notebook_uuid: str


class NotebookUpdate(BaseModel):
    """Notebook update schema."""

    visible_name: str | None = None
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


class NotebookUploadResponse(BaseModel):
    """Response after file upload."""

    notebook: Notebook
    message: str
