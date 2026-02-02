"""Search response schemas."""

from datetime import datetime

from pydantic import BaseModel, Field


class SearchSnippet(BaseModel):
    """A snippet of text around a search match."""

    text: str = Field(..., description="Snippet text around the match")
    highlights: list[tuple[int, int]] = Field(
        default_factory=list, description="List of (start, end) positions to highlight"
    )


class MatchedPage(BaseModel):
    """A page that matched the search query."""

    page_id: int
    page_uuid: str | None
    page_number: int
    snippet: SearchSnippet
    score: float = Field(..., ge=0, le=1, description="Relevance score (0-1)")


class SearchResult(BaseModel):
    """A notebook search result with matched pages."""

    notebook_id: int
    notebook_uuid: str
    visible_name: str
    document_type: str
    full_path: str | None
    name_match: bool = Field(..., description="Whether the notebook name matched")
    name_score: float = Field(
        ..., ge=0, le=1, description="Name match relevance score (0-1)"
    )
    matched_pages: list[MatchedPage] = Field(
        default_factory=list, description="Top matching pages (max 5)"
    )
    total_matched_pages: int = Field(
        ..., description="Total number of pages that matched"
    )
    best_score: float = Field(
        ..., ge=0, le=1, description="Best score across name and content matches"
    )
    updated_at: datetime


class SearchResponse(BaseModel):
    """Search API response."""

    query: str
    results: list[SearchResult]
    total_results: int
    has_more: bool
    search_mode: str = Field(
        ..., description="Search mode used: 'fuzzy' (PostgreSQL) or 'basic' (SQLite)"
    )
