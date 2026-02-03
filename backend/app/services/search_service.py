"""Search service with database-specific backends for fuzzy full-text search."""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.notebook import Notebook
from app.models.notebook_page import NotebookPage
from app.models.page import Page
from app.schemas.search import (
    MatchedPage,
    SearchResponse,
    SearchResult,
    SearchSnippet,
)


@dataclass
class RawSearchMatch:
    """Raw search match from database query."""

    notebook_id: int
    notebook_uuid: str
    visible_name: str
    document_type: str
    full_path: str | None
    updated_at: any
    page_id: int | None
    page_uuid: str | None
    page_number: int | None
    ocr_text: str | None
    name_score: float
    content_score: float


class SearchBackend(ABC):
    """Abstract base class for search backends."""

    @property
    @abstractmethod
    def search_mode(self) -> str:
        """Return the search mode identifier."""
        pass

    @abstractmethod
    def search(
        self,
        db: Session,
        user_id: int,
        query: str,
        skip: int = 0,
        limit: int = 20,
        fuzzy_threshold: float = 0.3,
    ) -> tuple[list[RawSearchMatch], int]:
        """
        Execute search and return raw matches.

        Returns:
            Tuple of (matches, total_count)
        """
        pass


class PostgreSQLSearchBackend(SearchBackend):
    """PostgreSQL search backend using pg_trgm for fuzzy matching."""

    @property
    def search_mode(self) -> str:
        return "fuzzy"

    def search(
        self,
        db: Session,
        user_id: int,
        query: str,
        skip: int = 0,
        limit: int = 20,
        fuzzy_threshold: float = 0.3,
    ) -> tuple[list[RawSearchMatch], int]:
        # Set similarity thresholds for session
        # - similarity_threshold: for notebook name matching (short text)
        # - strict_word_similarity_threshold: for OCR content matching (long text)
        db.execute(
            text(f"SET pg_trgm.similarity_threshold = {fuzzy_threshold}")
        )
        db.execute(
            text(f"SET pg_trgm.strict_word_similarity_threshold = {fuzzy_threshold}")
        )

        # Query for notebook name matches
        name_matches_sql = text("""
            SELECT
                n.id as notebook_id,
                n.notebook_uuid,
                n.visible_name,
                n.document_type,
                n.full_path,
                n.updated_at,
                NULL::integer as page_id,
                NULL::text as page_uuid,
                NULL::integer as page_number,
                NULL::text as ocr_text,
                similarity(n.visible_name, :query) as name_score,
                0.0::float as content_score
            FROM notebooks n
            WHERE n.user_id = :user_id
              AND n.deleted = false
              AND n.visible_name % :query
        """)

        # Query for content matches using strict_word_similarity
        # Note: Regular pg_trgm similarity() doesn't work for long text because
        # it calculates similarity over the entire string, diluting matches.
        # strict_word_similarity finds if the query appears as a similar WORD
        # within the text, which is ideal for OCR content with potential typos.
        content_matches_sql = text("""
            SELECT
                n.id as notebook_id,
                n.notebook_uuid,
                n.visible_name,
                n.document_type,
                n.full_path,
                n.updated_at,
                p.id as page_id,
                p.page_uuid,
                np.page_number,
                p.ocr_text,
                0.0::float as name_score,
                strict_word_similarity(:query, p.ocr_text) as content_score
            FROM pages p
            JOIN notebook_pages np ON np.page_id = p.id
            JOIN notebooks n ON n.id = np.notebook_id
            WHERE n.user_id = :user_id
              AND n.deleted = false
              AND :query <<% p.ocr_text
              AND p.ocr_status = 'completed'
        """)

        # Combined query with pagination
        combined_sql = text("""
            WITH combined AS (
                (""" + name_matches_sql.text + """)
                UNION ALL
                (""" + content_matches_sql.text + """)
            )
            SELECT * FROM combined
            ORDER BY GREATEST(name_score, content_score) DESC
            LIMIT :limit OFFSET :skip
        """)

        # Count query
        count_sql = text("""
            SELECT COUNT(DISTINCT notebook_id) FROM (
                (SELECT n.id as notebook_id
                 FROM notebooks n
                 WHERE n.user_id = :user_id
                   AND n.deleted = false
                   AND n.visible_name % :query)
                UNION
                (SELECT n.id as notebook_id
                 FROM pages p
                 JOIN notebook_pages np ON np.page_id = p.id
                 JOIN notebooks n ON n.id = np.notebook_id
                 WHERE n.user_id = :user_id
                   AND n.deleted = false
                   AND :query <<% p.ocr_text
                   AND p.ocr_status = 'completed')
            ) AS matched_notebooks
        """)

        params = {"user_id": user_id, "query": query, "skip": skip, "limit": limit}

        results = db.execute(combined_sql, params).fetchall()
        total_count = db.execute(count_sql, {"user_id": user_id, "query": query}).scalar()

        matches = [
            RawSearchMatch(
                notebook_id=row.notebook_id,
                notebook_uuid=row.notebook_uuid,
                visible_name=row.visible_name,
                document_type=row.document_type,
                full_path=row.full_path,
                updated_at=row.updated_at,
                page_id=row.page_id,
                page_uuid=row.page_uuid,
                page_number=row.page_number,
                ocr_text=row.ocr_text,
                name_score=float(row.name_score) if row.name_score else 0.0,
                content_score=float(row.content_score) if row.content_score else 0.0,
            )
            for row in results
        ]

        return matches, total_count or 0


class SQLiteSearchBackend(SearchBackend):
    """SQLite search backend using LIKE for basic matching."""

    @property
    def search_mode(self) -> str:
        return "basic"

    def search(
        self,
        db: Session,
        user_id: int,
        query: str,
        skip: int = 0,
        limit: int = 20,
        fuzzy_threshold: float = 0.3,
    ) -> tuple[list[RawSearchMatch], int]:
        # Use ORM queries for SQLite (LIKE-based)
        like_pattern = f"%{query}%"

        # Get notebook name matches
        name_matches = (
            db.query(Notebook)
            .filter(
                Notebook.user_id == user_id,
                Notebook.deleted == False,
                Notebook.visible_name.ilike(like_pattern),
            )
            .all()
        )

        # Get content matches
        content_matches = (
            db.query(Page, NotebookPage, Notebook)
            .join(NotebookPage, NotebookPage.page_id == Page.id)
            .join(Notebook, Notebook.id == NotebookPage.notebook_id)
            .filter(
                Notebook.user_id == user_id,
                Notebook.deleted == False,
                Page.ocr_text.ilike(like_pattern),
                Page.ocr_status == "completed",
            )
            .all()
        )

        # Build matches list
        matches: list[RawSearchMatch] = []

        for notebook in name_matches:
            matches.append(
                RawSearchMatch(
                    notebook_id=notebook.id,
                    notebook_uuid=notebook.notebook_uuid,
                    visible_name=notebook.visible_name,
                    document_type=notebook.document_type,
                    full_path=notebook.full_path,
                    updated_at=notebook.updated_at,
                    page_id=None,
                    page_uuid=None,
                    page_number=None,
                    ocr_text=None,
                    name_score=1.0,  # Binary match for SQLite
                    content_score=0.0,
                )
            )

        for page, notebook_page, notebook in content_matches:
            matches.append(
                RawSearchMatch(
                    notebook_id=notebook.id,
                    notebook_uuid=notebook.notebook_uuid,
                    visible_name=notebook.visible_name,
                    document_type=notebook.document_type,
                    full_path=notebook.full_path,
                    updated_at=notebook.updated_at,
                    page_id=page.id,
                    page_uuid=page.page_uuid,
                    page_number=notebook_page.page_number,
                    ocr_text=page.ocr_text,
                    name_score=0.0,
                    content_score=1.0,  # Binary match for SQLite
                )
            )

        # Sort by best score (name matches first, then content)
        matches.sort(
            key=lambda m: max(m.name_score, m.content_score),
            reverse=True,
        )

        # Get unique notebook count for total
        unique_notebook_ids = set(m.notebook_id for m in matches)
        total_count = len(unique_notebook_ids)

        # Apply pagination
        paginated_matches = matches[skip : skip + limit]

        return paginated_matches, total_count


def get_search_backend(db: Session) -> SearchBackend:
    """Factory function to get appropriate search backend based on database dialect."""
    dialect_name = db.bind.dialect.name
    if dialect_name == "postgresql":
        return PostgreSQLSearchBackend()
    return SQLiteSearchBackend()


def create_snippet(text: str, query: str, context_chars: int = 100) -> SearchSnippet:
    """
    Create a snippet with highlighted match positions.

    Args:
        text: Full text to extract snippet from
        query: Search query to find
        context_chars: Characters of context around match

    Returns:
        SearchSnippet with text and highlight positions
    """
    if not text or not query:
        return SearchSnippet(text="", highlights=[])

    # Find first case-insensitive match
    lower_text = text.lower()
    lower_query = query.lower()
    match_start = lower_text.find(lower_query)

    if match_start == -1:
        # No exact match found, return beginning of text
        snippet = text[:context_chars * 2]
        if len(text) > context_chars * 2:
            snippet += "..."
        return SearchSnippet(text=snippet, highlights=[])

    # Calculate snippet boundaries
    snippet_start = max(0, match_start - context_chars)
    snippet_end = min(len(text), match_start + len(query) + context_chars)

    # Extract snippet
    snippet = text[snippet_start:snippet_end]

    # Add ellipsis if truncated
    prefix = "..." if snippet_start > 0 else ""
    suffix = "..." if snippet_end < len(text) else ""

    # Calculate highlight position in snippet (accounting for prefix ellipsis)
    highlight_start = match_start - snippet_start + len(prefix)
    highlight_end = highlight_start + len(query)

    snippet_text = prefix + snippet + suffix

    return SearchSnippet(
        text=snippet_text,
        highlights=[(highlight_start, highlight_end)],
    )


def aggregate_results(
    matches: list[RawSearchMatch],
    query: str,
    max_pages_per_notebook: int = 5,
) -> list[SearchResult]:
    """
    Aggregate raw matches into SearchResult objects grouped by notebook.

    Args:
        matches: Raw search matches from backend
        query: Original search query (for snippet generation)
        max_pages_per_notebook: Maximum matched pages to include per notebook

    Returns:
        List of SearchResult objects
    """
    # Group matches by notebook
    notebook_matches: dict[int, dict] = {}

    for match in matches:
        notebook_id = match.notebook_id

        if notebook_id not in notebook_matches:
            notebook_matches[notebook_id] = {
                "notebook_id": match.notebook_id,
                "notebook_uuid": match.notebook_uuid,
                "visible_name": match.visible_name,
                "document_type": match.document_type,
                "full_path": match.full_path,
                "updated_at": match.updated_at,
                "name_match": False,
                "name_score": 0.0,
                "pages": [],
                "best_score": 0.0,
            }

        # Track name match
        if match.name_score > 0:
            notebook_matches[notebook_id]["name_match"] = True
            notebook_matches[notebook_id]["name_score"] = max(
                notebook_matches[notebook_id]["name_score"],
                match.name_score,
            )

        # Track content matches
        if match.page_id is not None and match.content_score > 0:
            notebook_matches[notebook_id]["pages"].append(match)

        # Track best score
        notebook_matches[notebook_id]["best_score"] = max(
            notebook_matches[notebook_id]["best_score"],
            match.name_score,
            match.content_score,
        )

    # Convert to SearchResult objects
    results: list[SearchResult] = []

    for notebook_id, data in notebook_matches.items():
        # Sort pages by score and take top N
        pages = sorted(data["pages"], key=lambda p: p.content_score, reverse=True)
        top_pages = pages[:max_pages_per_notebook]

        matched_pages = [
            MatchedPage(
                page_id=p.page_id,
                page_uuid=p.page_uuid,
                page_number=p.page_number,
                snippet=create_snippet(p.ocr_text or "", query),
                score=p.content_score,
            )
            for p in top_pages
        ]

        results.append(
            SearchResult(
                notebook_id=data["notebook_id"],
                notebook_uuid=data["notebook_uuid"],
                visible_name=data["visible_name"],
                document_type=data["document_type"],
                full_path=data["full_path"],
                name_match=data["name_match"],
                name_score=data["name_score"],
                matched_pages=matched_pages,
                total_matched_pages=len(pages),
                best_score=data["best_score"],
                updated_at=data["updated_at"],
            )
        )

    # Sort results by best score
    results.sort(key=lambda r: r.best_score, reverse=True)

    return results


def search(
    db: Session,
    user_id: int,
    query: str,
    skip: int = 0,
    limit: int = 20,
    fuzzy_threshold: float = 0.3,
) -> SearchResponse:
    """
    Execute full-text search across notebooks and pages.

    Args:
        db: Database session
        user_id: User ID to search for
        query: Search query string
        skip: Pagination offset
        limit: Maximum results to return
        fuzzy_threshold: Similarity threshold (0-1, PostgreSQL only)

    Returns:
        SearchResponse with results and metadata
    """
    backend = get_search_backend(db)

    # Fetch more than limit to properly count pages per notebook
    # We'll aggregate and then trim to actual limit
    raw_matches, total_notebooks = backend.search(
        db=db,
        user_id=user_id,
        query=query,
        skip=0,  # Get all for proper aggregation
        limit=limit * 10,  # Fetch extra for page aggregation
        fuzzy_threshold=fuzzy_threshold,
    )

    # Aggregate into SearchResult objects
    all_results = aggregate_results(raw_matches, query)

    # Apply pagination to aggregated results
    paginated_results = all_results[skip : skip + limit]

    return SearchResponse(
        query=query,
        results=paginated_results,
        total_results=total_notebooks,
        has_more=skip + len(paginated_results) < total_notebooks,
        search_mode=backend.search_mode,
    )
