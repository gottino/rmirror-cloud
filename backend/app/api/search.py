"""Search API endpoint for full-text fuzzy search across notebooks and pages."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth.clerk import get_clerk_active_user
from app.database import get_db
from app.models.user import User
from app.schemas.search import SearchResponse
from app.services import search_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("", response_model=SearchResponse)
async def search_notebooks(
    q: Annotated[
        str,
        Query(
            min_length=2,
            max_length=200,
            description="Search query (2-200 characters)",
        ),
    ],
    current_user: Annotated[User, Depends(get_clerk_active_user)],
    db: Annotated[Session, Depends(get_db)],
    skip: Annotated[int, Query(ge=0, description="Pagination offset")] = 0,
    limit: Annotated[
        int, Query(ge=1, le=50, description="Results per page (1-50)")
    ] = 20,
    fuzzy_threshold: Annotated[
        float,
        Query(
            ge=0.0,
            le=1.0,
            description="Similarity threshold (0-1, PostgreSQL only). Lower = more fuzzy.",
        ),
    ] = 0.3,
):
    """
    Search across notebook names and OCR page content.

    Uses fuzzy trigram matching on PostgreSQL (catches OCR errors like
    'meeting' vs 'meeling') and basic LIKE matching on SQLite.

    The search_mode field in the response indicates which backend was used:
    - "fuzzy": PostgreSQL pg_trgm similarity matching
    - "basic": SQLite LIKE pattern matching

    Args:
        q: Search query string (2-200 chars)
        current_user: Authenticated user
        db: Database session
        skip: Pagination offset (default 0)
        limit: Results per page (default 20, max 50)
        fuzzy_threshold: Similarity threshold for fuzzy matching (default 0.3)

    Returns:
        SearchResponse with matching notebooks, pages, and snippets
    """
    logger.info(f"Search request: user={current_user.id}, query='{q}', skip={skip}, limit={limit}")

    result = search_service.search(
        db=db,
        user_id=current_user.id,
        query=q,
        skip=skip,
        limit=limit,
        fuzzy_threshold=fuzzy_threshold,
    )

    logger.info(
        f"Search completed: {result.total_results} results, mode={result.search_mode}"
    )

    return result
