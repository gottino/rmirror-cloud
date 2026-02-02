"""Tests for the search service.

Tests cover:
- SQLite backend (LIKE-based search) for local development
- Snippet generation with highlights
- Result aggregation by notebook
- Edge cases (empty results, special characters)
"""

from datetime import datetime

import pytest
from sqlalchemy.orm import Session

from app.models.notebook import Notebook
from app.models.notebook_page import NotebookPage
from app.models.page import OcrStatus, Page
from app.models.user import User
from app.services import search_service
from app.services.search_service import (
    SQLiteSearchBackend,
    aggregate_results,
    create_snippet,
    get_search_backend,
    RawSearchMatch,
)
from tests.conftest import create_user_with_quota


class TestGetSearchBackend:
    """Tests for search backend detection."""

    def test_sqlite_backend_selected_for_sqlite(self, db: Session):
        """SQLite database should use SQLiteSearchBackend."""
        backend = get_search_backend(db)
        assert isinstance(backend, SQLiteSearchBackend)
        assert backend.search_mode == "basic"


class TestCreateSnippet:
    """Tests for snippet generation."""

    def test_creates_snippet_with_highlight(self):
        """Should create snippet with correct highlight positions."""
        text = "This is a test document about meetings and notes."
        snippet = create_snippet(text, "meeting")

        assert "meeting" in snippet.text.lower()
        assert len(snippet.highlights) == 1
        start, end = snippet.highlights[0]
        assert snippet.text[start:end].lower() == "meeting"

    def test_adds_ellipsis_for_long_text(self):
        """Should add ellipsis when truncating long text."""
        text = "A" * 50 + " meeting " + "B" * 200
        snippet = create_snippet(text, "meeting", context_chars=50)

        assert snippet.text.startswith("...")
        assert snippet.text.endswith("...")
        assert "meeting" in snippet.text

    def test_no_prefix_ellipsis_at_start(self):
        """Should not add prefix ellipsis when match is near start."""
        text = "meeting is the topic of this document"
        snippet = create_snippet(text, "meeting", context_chars=100)

        assert not snippet.text.startswith("...")
        assert "meeting" in snippet.text

    def test_no_suffix_ellipsis_at_end(self):
        """Should not add suffix ellipsis when match is near end."""
        text = "The topic is meeting"
        snippet = create_snippet(text, "meeting", context_chars=100)

        assert not snippet.text.endswith("...")

    def test_case_insensitive_matching(self):
        """Should find matches regardless of case."""
        text = "The MEETING was productive"
        snippet = create_snippet(text, "meeting")

        assert len(snippet.highlights) == 1
        assert "MEETING" in snippet.text

    def test_empty_text_returns_empty_snippet(self):
        """Should handle empty text gracefully."""
        snippet = create_snippet("", "meeting")

        assert snippet.text == ""
        assert snippet.highlights == []

    def test_no_match_returns_beginning_of_text(self):
        """Should return beginning of text when no match found."""
        text = "This document has no relevant content"
        snippet = create_snippet(text, "xyz123")

        assert snippet.text.startswith("This document")
        assert snippet.highlights == []


class TestAggregateResults:
    """Tests for result aggregation."""

    def test_groups_by_notebook(self):
        """Should group matches by notebook ID."""
        matches = [
            RawSearchMatch(
                notebook_id=1,
                notebook_uuid="nb-1",
                visible_name="Notebook 1",
                document_type="notebook",
                full_path="/path/1",
                updated_at=datetime.utcnow(),
                page_id=10,
                page_uuid="p-10",
                page_number=1,
                ocr_text="meeting notes",
                name_score=0.0,
                content_score=0.8,
            ),
            RawSearchMatch(
                notebook_id=1,
                notebook_uuid="nb-1",
                visible_name="Notebook 1",
                document_type="notebook",
                full_path="/path/1",
                updated_at=datetime.utcnow(),
                page_id=11,
                page_uuid="p-11",
                page_number=2,
                ocr_text="more meeting content",
                name_score=0.0,
                content_score=0.6,
            ),
            RawSearchMatch(
                notebook_id=2,
                notebook_uuid="nb-2",
                visible_name="Notebook 2",
                document_type="notebook",
                full_path="/path/2",
                updated_at=datetime.utcnow(),
                page_id=20,
                page_uuid="p-20",
                page_number=1,
                ocr_text="different meeting",
                name_score=0.0,
                content_score=0.7,
            ),
        ]

        results = aggregate_results(matches, "meeting")

        assert len(results) == 2
        nb1_result = next(r for r in results if r.notebook_id == 1)
        assert len(nb1_result.matched_pages) == 2
        assert nb1_result.total_matched_pages == 2

    def test_tracks_name_match(self):
        """Should track when notebook name matched."""
        matches = [
            RawSearchMatch(
                notebook_id=1,
                notebook_uuid="nb-1",
                visible_name="Meeting Notes",
                document_type="notebook",
                full_path="/path/1",
                updated_at=datetime.utcnow(),
                page_id=None,
                page_uuid=None,
                page_number=None,
                ocr_text=None,
                name_score=0.9,
                content_score=0.0,
            ),
        ]

        results = aggregate_results(matches, "meeting")

        assert len(results) == 1
        assert results[0].name_match is True
        assert results[0].name_score == 0.9

    def test_limits_pages_per_notebook(self):
        """Should limit matched pages per notebook."""
        matches = [
            RawSearchMatch(
                notebook_id=1,
                notebook_uuid="nb-1",
                visible_name="Notebook",
                document_type="notebook",
                full_path="/path",
                updated_at=datetime.utcnow(),
                page_id=i,
                page_uuid=f"p-{i}",
                page_number=i,
                ocr_text="meeting content",
                name_score=0.0,
                content_score=0.8 - (i * 0.01),
            )
            for i in range(10)
        ]

        results = aggregate_results(matches, "meeting", max_pages_per_notebook=5)

        assert len(results) == 1
        assert len(results[0].matched_pages) == 5
        assert results[0].total_matched_pages == 10

    def test_sorts_by_best_score(self):
        """Should sort results by best score descending."""
        matches = [
            RawSearchMatch(
                notebook_id=1,
                notebook_uuid="nb-1",
                visible_name="Low Score",
                document_type="notebook",
                full_path="/path/1",
                updated_at=datetime.utcnow(),
                page_id=10,
                page_uuid="p-10",
                page_number=1,
                ocr_text="meeting",
                name_score=0.0,
                content_score=0.3,
            ),
            RawSearchMatch(
                notebook_id=2,
                notebook_uuid="nb-2",
                visible_name="High Score",
                document_type="notebook",
                full_path="/path/2",
                updated_at=datetime.utcnow(),
                page_id=20,
                page_uuid="p-20",
                page_number=1,
                ocr_text="meeting",
                name_score=0.0,
                content_score=0.9,
            ),
        ]

        results = aggregate_results(matches, "meeting")

        assert results[0].notebook_id == 2  # Higher score first
        assert results[1].notebook_id == 1


class TestSQLiteSearchBackend:
    """Tests for SQLite search backend (used in local development)."""

    @pytest.fixture
    def search_user(self, db: Session) -> User:
        """Create a user for search tests."""
        return create_user_with_quota(db, email="search@test.com")

    @pytest.fixture
    def notebook_with_pages(self, db: Session, search_user: User) -> tuple[Notebook, list[Page]]:
        """Create a notebook with pages containing OCR text."""
        notebook = Notebook(
            notebook_uuid="test-notebook-uuid",
            user_id=search_user.id,
            visible_name="Meeting Notes 2026",
            document_type="notebook",
            full_path="/Work/Meetings",
            deleted=False,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(notebook)
        db.commit()
        db.refresh(notebook)

        pages = []
        ocr_texts = [
            "Discussion about project timeline and deliverables",
            "Meeting with stakeholders about budget",
            "Notes from quarterly review session",
        ]

        for i, text in enumerate(ocr_texts):
            page = Page(
                notebook_id=notebook.id,
                page_uuid=f"page-uuid-{i}",
                ocr_status=OcrStatus.COMPLETED,
                ocr_text=text,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            db.add(page)
            db.commit()
            db.refresh(page)

            # Create notebook_page mapping
            notebook_page = NotebookPage(
                notebook_id=notebook.id,
                page_id=page.id,
                page_number=i + 1,
            )
            db.add(notebook_page)
            pages.append(page)

        db.commit()
        return notebook, pages

    def test_finds_notebook_by_name(self, db: Session, search_user: User, notebook_with_pages):
        """Should find notebooks by visible_name."""
        notebook, _ = notebook_with_pages

        response = search_service.search(
            db=db,
            user_id=search_user.id,
            query="Meeting",
            skip=0,
            limit=20,
        )

        assert response.search_mode == "basic"
        assert response.total_results >= 1
        assert any(r.notebook_uuid == notebook.notebook_uuid for r in response.results)

    def test_finds_pages_by_content(self, db: Session, search_user: User, notebook_with_pages):
        """Should find pages by OCR content."""
        notebook, _ = notebook_with_pages

        response = search_service.search(
            db=db,
            user_id=search_user.id,
            query="stakeholders",
            skip=0,
            limit=20,
        )

        assert response.total_results >= 1
        result = next(r for r in response.results if r.notebook_uuid == notebook.notebook_uuid)
        assert len(result.matched_pages) >= 1
        assert any("stakeholder" in p.snippet.text.lower() for p in result.matched_pages)

    def test_excludes_deleted_notebooks(self, db: Session, search_user: User):
        """Should not return deleted notebooks."""
        notebook = Notebook(
            notebook_uuid="deleted-notebook-uuid",
            user_id=search_user.id,
            visible_name="Deleted Meeting Notes",
            document_type="notebook",
            deleted=True,  # Marked as deleted
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(notebook)
        db.commit()

        response = search_service.search(
            db=db,
            user_id=search_user.id,
            query="Deleted Meeting",
            skip=0,
            limit=20,
        )

        assert not any(r.notebook_uuid == "deleted-notebook-uuid" for r in response.results)

    def test_excludes_other_users_notebooks(self, db: Session, search_user: User, notebook_with_pages):
        """Should not return notebooks from other users."""
        other_user = create_user_with_quota(db, email="other@test.com")

        response = search_service.search(
            db=db,
            user_id=other_user.id,
            query="Meeting",
            skip=0,
            limit=20,
        )

        # Other user should not see search_user's notebooks
        assert not any(r.notebook_uuid == "test-notebook-uuid" for r in response.results)

    def test_excludes_pages_without_completed_ocr(self, db: Session, search_user: User):
        """Should not return pages that don't have completed OCR."""
        notebook = Notebook(
            notebook_uuid="pending-ocr-notebook",
            user_id=search_user.id,
            visible_name="Pending OCR Notebook",
            document_type="notebook",
            deleted=False,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(notebook)
        db.commit()
        db.refresh(notebook)

        # Create page with pending OCR
        page = Page(
            notebook_id=notebook.id,
            page_uuid="pending-page-uuid",
            ocr_status=OcrStatus.PENDING,  # Not completed
            ocr_text="searchable unique content xyz123",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(page)
        db.commit()

        notebook_page = NotebookPage(
            notebook_id=notebook.id,
            page_id=page.id,
            page_number=1,
        )
        db.add(notebook_page)
        db.commit()

        response = search_service.search(
            db=db,
            user_id=search_user.id,
            query="xyz123",
            skip=0,
            limit=20,
        )

        # Should not find the pending page content
        for result in response.results:
            for mp in result.matched_pages:
                assert "xyz123" not in mp.snippet.text

    def test_returns_empty_for_no_matches(self, db: Session, search_user: User, notebook_with_pages):
        """Should return empty results for non-matching query."""
        response = search_service.search(
            db=db,
            user_id=search_user.id,
            query="xyznonexistent123",
            skip=0,
            limit=20,
        )

        assert response.total_results == 0
        assert response.results == []
        assert response.has_more is False

    def test_pagination_skip(self, db: Session, search_user: User):
        """Should correctly skip results for pagination."""
        # Create multiple notebooks
        for i in range(5):
            notebook = Notebook(
                notebook_uuid=f"paginated-nb-{i}",
                user_id=search_user.id,
                visible_name=f"Searchable Notebook {i}",
                document_type="notebook",
                deleted=False,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            db.add(notebook)
        db.commit()

        # Get first 2
        response1 = search_service.search(
            db=db,
            user_id=search_user.id,
            query="Searchable",
            skip=0,
            limit=2,
        )

        # Get next 2
        response2 = search_service.search(
            db=db,
            user_id=search_user.id,
            query="Searchable",
            skip=2,
            limit=2,
        )

        # Results should be different
        ids1 = {r.notebook_id for r in response1.results}
        ids2 = {r.notebook_id for r in response2.results}
        assert ids1.isdisjoint(ids2)

    def test_pagination_limit(self, db: Session, search_user: User):
        """Should respect limit parameter."""
        # Create multiple notebooks
        for i in range(10):
            notebook = Notebook(
                notebook_uuid=f"limited-nb-{i}",
                user_id=search_user.id,
                visible_name=f"Limited Notebook {i}",
                document_type="notebook",
                deleted=False,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            db.add(notebook)
        db.commit()

        response = search_service.search(
            db=db,
            user_id=search_user.id,
            query="Limited",
            skip=0,
            limit=3,
        )

        assert len(response.results) == 3
        assert response.has_more is True

    def test_case_insensitive_search(self, db: Session, search_user: User, notebook_with_pages):
        """Should perform case-insensitive search."""
        response_lower = search_service.search(
            db=db,
            user_id=search_user.id,
            query="meeting",
            skip=0,
            limit=20,
        )

        response_upper = search_service.search(
            db=db,
            user_id=search_user.id,
            query="MEETING",
            skip=0,
            limit=20,
        )

        # Both should find the same notebooks
        ids_lower = {r.notebook_uuid for r in response_lower.results}
        ids_upper = {r.notebook_uuid for r in response_upper.results}
        assert ids_lower == ids_upper


class TestSearchResponseStructure:
    """Tests for search response structure."""

    @pytest.fixture
    def search_user(self, db: Session) -> User:
        """Create a user for search tests."""
        return create_user_with_quota(db, email="structure@test.com")

    def test_response_includes_query(self, db: Session, search_user: User):
        """Response should include the original query."""
        response = search_service.search(
            db=db,
            user_id=search_user.id,
            query="test query",
            skip=0,
            limit=20,
        )

        assert response.query == "test query"

    def test_response_includes_search_mode(self, db: Session, search_user: User):
        """Response should indicate search mode used."""
        response = search_service.search(
            db=db,
            user_id=search_user.id,
            query="test",
            skip=0,
            limit=20,
        )

        assert response.search_mode in ("basic", "fuzzy")

    def test_matched_page_has_required_fields(self, db: Session, search_user: User):
        """MatchedPage should have all required fields."""
        notebook = Notebook(
            notebook_uuid="structure-test-nb",
            user_id=search_user.id,
            visible_name="Structure Test",
            document_type="notebook",
            deleted=False,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(notebook)
        db.commit()
        db.refresh(notebook)

        page = Page(
            notebook_id=notebook.id,
            page_uuid="structure-page-uuid",
            ocr_status=OcrStatus.COMPLETED,
            ocr_text="unique searchable content for structure test",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(page)
        db.commit()
        db.refresh(page)

        notebook_page = NotebookPage(
            notebook_id=notebook.id,
            page_id=page.id,
            page_number=1,
        )
        db.add(notebook_page)
        db.commit()

        response = search_service.search(
            db=db,
            user_id=search_user.id,
            query="unique searchable",
            skip=0,
            limit=20,
        )

        assert len(response.results) >= 1
        result = next(r for r in response.results if r.notebook_uuid == "structure-test-nb")
        assert len(result.matched_pages) >= 1

        matched_page = result.matched_pages[0]
        assert matched_page.page_id is not None
        assert matched_page.page_number is not None
        assert matched_page.snippet is not None
        assert matched_page.score >= 0
        assert matched_page.score <= 1

    def test_search_result_has_required_fields(self, db: Session, search_user: User):
        """SearchResult should have all required fields."""
        notebook = Notebook(
            notebook_uuid="result-test-nb",
            user_id=search_user.id,
            visible_name="Result Field Test",
            document_type="notebook",
            full_path="/Test/Path",
            deleted=False,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(notebook)
        db.commit()

        response = search_service.search(
            db=db,
            user_id=search_user.id,
            query="Result Field",
            skip=0,
            limit=20,
        )

        assert len(response.results) >= 1
        result = next(r for r in response.results if r.notebook_uuid == "result-test-nb")

        assert result.notebook_id is not None
        assert result.notebook_uuid == "result-test-nb"
        assert result.visible_name == "Result Field Test"
        assert result.document_type == "notebook"
        assert result.full_path == "/Test/Path"
        assert isinstance(result.name_match, bool)
        assert result.name_score >= 0
        assert result.best_score >= 0
        assert result.updated_at is not None
