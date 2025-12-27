"""Page schemas."""

from datetime import datetime

from pydantic import BaseModel


class PageBase(BaseModel):
    """Base page schema."""

    page_number: int


class Page(PageBase):
    """Page response schema."""

    id: int
    notebook_id: int
    page_uuid: str | None = None
    ocr_status: str
    ocr_text: str | None = None
    ocr_error: str | None = None
    pdf_s3_key: str | None = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
