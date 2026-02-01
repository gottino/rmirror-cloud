"""Test configuration and fixtures for pytest.

Provides fixtures for:
- In-memory SQLite database
- Test users with quota states
- Rate limiter reset
- Test data factories
"""

from datetime import datetime, timedelta
from pathlib import Path
from typing import Generator
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.notebook import Notebook
from app.models.page import OcrStatus, Page
from app.models.quota_usage import QuotaType, QuotaUsage
from app.models.subscription import Subscription, SubscriptionStatus, SubscriptionTier
from app.models.user import User

# Test database URL (in-memory SQLite)
TEST_DATABASE_URL = "sqlite:///:memory:"


# Register custom pytest marks
def pytest_configure(config):
    """Register custom pytest markers."""
    config.addinivalue_line("markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')")


@pytest.fixture(scope="function")
def db_engine():
    """Create a test database engine."""
    engine = create_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture(scope="function")
def db(db_engine) -> Generator[Session, None, None]:
    """Create a test database session."""
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    session = TestSessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def test_user(db: Session) -> User:
    """Create a test user with free tier subscription."""
    user = User(
        email="test@example.com",
        full_name="Test User",
        clerk_user_id=f"clerk_test_{datetime.utcnow().timestamp()}",
        subscription_tier=SubscriptionTier.FREE,
        is_active=True,
        is_verified=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # Create subscription
    subscription = Subscription(
        user_id=user.id,
        tier=SubscriptionTier.FREE,
        status=SubscriptionStatus.ACTIVE,
        current_period_start=datetime.utcnow(),
        current_period_end=datetime.utcnow() + timedelta(days=30),
    )
    db.add(subscription)
    db.commit()

    return user


@pytest.fixture
def test_notebook(db: Session, test_user: User) -> Notebook:
    """Create a test notebook."""
    notebook = Notebook(
        uuid=f"test-notebook-{datetime.utcnow().timestamp()}",
        user_id=test_user.id,
        visible_name="Test Notebook",
        created_at=datetime.utcnow(),
    )
    db.add(notebook)
    db.commit()
    db.refresh(notebook)
    return notebook


def create_user_with_quota(
    db: Session,
    email: str = None,
    used: int = 0,
    limit: int = 30,
    tier: str = SubscriptionTier.FREE,
) -> User:
    """Helper to create a user with specific quota state."""
    if email is None:
        email = f"user_{datetime.utcnow().timestamp()}@example.com"

    user = User(
        email=email,
        full_name="Test User",
        clerk_user_id=f"clerk_test_{datetime.utcnow().timestamp()}",
        subscription_tier=tier,
        is_active=True,
        is_verified=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # Create subscription
    subscription = Subscription(
        user_id=user.id,
        tier=tier,
        status=SubscriptionStatus.ACTIVE,
        current_period_start=datetime.utcnow(),
        current_period_end=datetime.utcnow() + timedelta(days=30),
    )
    db.add(subscription)
    db.commit()

    # Create quota
    quota = QuotaUsage(
        user_id=user.id,
        quota_type=QuotaType.OCR,
        limit=limit,
        used=used,
        reset_at=datetime.utcnow() + timedelta(days=30),
        period_start=datetime.utcnow(),
    )
    db.add(quota)
    db.commit()

    return user


def create_test_page(
    db: Session,
    user_id: int,
    notebook_id: int,
    page_number: int = 1,
    ocr_status: str = OcrStatus.COMPLETED,
    created_at: datetime = None,
    ocr_text: str = None,
) -> Page:
    """Helper to create a test page."""
    if created_at is None:
        created_at = datetime.utcnow()

    if ocr_text is None and ocr_status == OcrStatus.COMPLETED:
        ocr_text = f"Test OCR text for page {page_number}"

    page = Page(
        notebook_id=notebook_id,
        page_uuid=f"page-{page_number}-{datetime.utcnow().timestamp()}",
        pdf_s3_key=f"s3://test-bucket/page-{page_number}.pdf",
        file_hash=f"hash-{page_number}",
        ocr_status=ocr_status,
        ocr_text=ocr_text,
        created_at=created_at,
        updated_at=created_at,
    )
    db.add(page)
    db.commit()
    db.refresh(page)
    return page


def create_pending_pages(
    db: Session,
    user_id: int,
    notebook_id: int,
    count: int,
    status: str = OcrStatus.PENDING_QUOTA,
) -> list[Page]:
    """Helper to create multiple pending pages with staggered timestamps."""
    pages = []
    for i in range(count):
        # Create pages with timestamps from oldest to newest
        created_at = datetime.utcnow() - timedelta(days=count - i)
        page = create_test_page(
            db=db,
            user_id=user_id,
            notebook_id=notebook_id,
            page_number=i,
            ocr_status=status,
            created_at=created_at,
            ocr_text=None,
        )
        pages.append(page)
    return pages


@pytest.fixture
def user_with_quota():
    """Fixture factory for creating users with specific quota states."""
    return create_user_with_quota


@pytest.fixture
def reset_rate_limiter():
    """Reset the rate limiter state between tests.

    This fixture clears the in-memory storage used by SlowAPI
    to ensure rate limits don't persist between tests.
    """
    # Import the limiter from the processing module
    from app.api.processing import limiter

    # Clear the limiter storage before test
    if hasattr(limiter, '_storage') and limiter._storage:
        limiter._storage.reset()

    yield limiter

    # Clear again after test for clean state
    if hasattr(limiter, '_storage') and limiter._storage:
        limiter._storage.reset()


@pytest.fixture
def mock_ocr_service():
    """Mock OCR service for tests that don't need actual OCR."""
    with patch("app.api.processing.OCRService") as mock_class:
        mock_instance = MagicMock()

        async def mock_extract_text(pdf_bytes):
            return "Mocked OCR text for testing"

        mock_instance.extract_text_from_pdf = mock_extract_text
        mock_class.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_storage_service():
    """Mock storage service for tests that don't need actual S3/B2."""
    from unittest.mock import AsyncMock

    mock_storage = MagicMock()
    mock_storage.upload_file = AsyncMock()
    mock_storage.download_file = AsyncMock(return_value=b"fake_pdf_bytes")
    mock_storage.delete_file = AsyncMock()
    mock_storage.file_exists = AsyncMock(return_value=True)
    mock_storage.get_file_url = MagicMock(return_value="https://example.com/fake.pdf")

    return mock_storage


# =============================================================================
# Named User Fixtures for Common Test Scenarios
# =============================================================================


@pytest.fixture
def fresh_user(db: Session) -> User:
    """User with 0/30 quota - new user flow testing."""
    return create_user_with_quota(
        db, email="fresh@test.com", used=0, limit=30, tier=SubscriptionTier.FREE
    )


@pytest.fixture
def active_user(db: Session) -> User:
    """User with 15/30 quota - normal usage testing."""
    return create_user_with_quota(
        db, email="active@test.com", used=15, limit=30, tier=SubscriptionTier.FREE
    )


@pytest.fixture
def warning_user(db: Session) -> User:
    """User with 27/30 quota (90%) - warning threshold testing."""
    return create_user_with_quota(
        db, email="warning@test.com", used=27, limit=30, tier=SubscriptionTier.FREE
    )


@pytest.fixture
def exhausted_user(db: Session) -> User:
    """User with 30/30 quota - graceful degradation testing."""
    return create_user_with_quota(
        db, email="exhausted@test.com", used=30, limit=30, tier=SubscriptionTier.FREE
    )


@pytest.fixture
def hardcap_user(db: Session) -> tuple[User, Notebook, list[Page]]:
    """User with 30/30 quota + 100 pending pages - hard cap testing.

    Returns tuple of (user, notebook, pending_pages).
    """
    user = create_user_with_quota(
        db, email="hardcap@test.com", used=30, limit=30, tier=SubscriptionTier.FREE
    )

    # Create notebook for pending pages
    notebook = Notebook(
        uuid=f"hardcap-notebook-{datetime.utcnow().timestamp()}",
        user_id=user.id,
        visible_name="Hard Cap Test Notebook",
        created_at=datetime.utcnow(),
    )
    db.add(notebook)
    db.commit()
    db.refresh(notebook)

    # Create 100 pending pages
    pending_pages = create_pending_pages(
        db=db,
        user_id=user.id,
        notebook_id=notebook.id,
        count=100,
        status=OcrStatus.PENDING_QUOTA,
    )

    return user, notebook, pending_pages


@pytest.fixture
def pro_user(db: Session) -> User:
    """User with 150/500 Pro tier quota - paid tier testing."""
    return create_user_with_quota(
        db, email="pro@test.com", used=150, limit=500, tier=SubscriptionTier.PRO
    )


# =============================================================================
# Fixture File Paths
# =============================================================================


@pytest.fixture
def fixtures_dir() -> Path:
    """Return path to the fixtures directory."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def valid_rm_file(fixtures_dir: Path) -> Path:
    """Return path to a valid .rm file fixture."""
    return fixtures_dir / "page_1.rm"


@pytest.fixture
def empty_rm_file(fixtures_dir: Path) -> Path:
    """Return path to an empty .rm file fixture."""
    return fixtures_dir / "empty_page.rm"


@pytest.fixture
def corrupted_rm_file(fixtures_dir: Path) -> Path:
    """Return path to a corrupted .rm file fixture."""
    return fixtures_dir / "corrupted_page.rm"


@pytest.fixture
def sample_metadata_file(fixtures_dir: Path) -> Path:
    """Return path to a sample notebook.metadata file."""
    return fixtures_dir / "notebook.metadata"


@pytest.fixture
def sample_content_file(fixtures_dir: Path) -> Path:
    """Return path to a sample notebook.content file."""
    return fixtures_dir / "notebook.content"


@pytest.fixture
def folder_metadata_file(fixtures_dir: Path) -> Path:
    """Return path to a folder.metadata file."""
    return fixtures_dir / "folder.metadata"


# =============================================================================
# Notion Integration Fixtures
# =============================================================================


@pytest.fixture
def mock_notion_client():
    """Mock Notion SDK client for testing Notion integrations."""
    with patch("notion_client.Client") as mock_class:
        mock_instance = MagicMock()

        # Configure common return values
        mock_instance.search.return_value = {"results": []}
        mock_instance.databases.retrieve.return_value = {
            "id": "db-123",
            "title": [{"plain_text": "Test Database"}],
            "properties": {},
        }
        mock_instance.pages.create.return_value = {"id": "page-123"}
        mock_instance.pages.update.return_value = {"id": "page-123"}
        mock_instance.blocks.children.list.return_value = {"results": [], "has_more": False}
        mock_instance.blocks.children.append.return_value = {"results": [{"id": "block-123"}]}
        mock_instance.blocks.delete.return_value = {}

        mock_class.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_httpx_client():
    """Mock httpx client for raw API calls in Notion tests."""
    with patch("httpx.Client") as mock_class:
        mock_instance = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "db-123", "url": "https://notion.so/db-123"}
        mock_response.raise_for_status.return_value = None

        mock_instance.post.return_value = mock_response
        mock_instance.patch.return_value = mock_response
        mock_instance.close.return_value = None

        mock_class.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_httpx_async_client():
    """Mock async httpx client for OAuth token exchange."""
    from unittest.mock import AsyncMock

    with patch("httpx.AsyncClient") as mock_class:
        mock_instance = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "test-access-token",
            "workspace_id": "ws-123",
            "workspace_name": "Test Workspace",
            "bot_id": "bot-123",
            "owner": {"type": "user"},
        }
        mock_response.raise_for_status.return_value = None

        mock_instance.post = AsyncMock(return_value=mock_response)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=None)

        mock_class.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def notion_oauth_settings():
    """Mock settings for Notion OAuth tests."""
    mock_settings = MagicMock()
    mock_settings.notion_client_id = "test-client-id"
    mock_settings.notion_client_secret = "test-secret"
    mock_settings.notion_redirect_uri = "http://localhost:3000/callback"
    mock_settings.debug = True
    return mock_settings


@pytest.fixture
def sample_notion_database_response():
    """Sample Notion database API response for testing."""
    return {
        "id": "db-123",
        "object": "database",
        "title": [{"type": "text", "text": {"content": "Test Database"}, "plain_text": "Test Database"}],
        "url": "https://notion.so/db-123",
        "created_time": "2026-01-01T00:00:00.000Z",
        "last_edited_time": "2026-01-15T12:00:00.000Z",
        "properties": {
            "Name": {"id": "title", "type": "title"},
            "UUID": {"id": "uuid", "type": "rich_text"},
            "Status": {"id": "status", "type": "status"},
            "Workflow": {"id": "workflow", "type": "select"},
        },
        "data_sources": [{"id": "ds-456"}],
    }


@pytest.fixture
def sample_notion_page_response():
    """Sample Notion page API response for testing."""
    return {
        "id": "page-123",
        "object": "page",
        "parent": {"type": "database_id", "database_id": "db-123"},
        "url": "https://notion.so/page-123",
        "created_time": "2026-01-01T00:00:00.000Z",
        "properties": {
            "Name": {
                "type": "title",
                "title": [{"type": "text", "text": {"content": "Test Page"}, "plain_text": "Test Page"}],
            },
            "UUID": {"type": "rich_text", "rich_text": [{"text": {"content": "nb-123"}}]},
        },
    }


@pytest.fixture
def sample_todo_sync_item():
    """Sample SyncItem for todo syncing."""
    from app.core.sync_engine import SyncItem
    from app.models.sync_record import SyncItemType

    return SyncItem(
        item_type=SyncItemType.TODO,
        item_id="todo-123",
        content_hash="abc123def456",
        data={
            "text": "Buy groceries",
            "is_completed": False,
            "notebook_uuid": "nb-123",
            "notebook_name": "Shopping List",
            "page_number": 1,
            "confidence": 0.95,
            "date_extracted": "2026-01-15T10:00:00",
            "source_link": "https://example.com/notebook/nb-123",
        },
        source_table="todos",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )


@pytest.fixture
def sample_notebook_sync_item():
    """Sample SyncItem for notebook syncing."""
    from app.core.sync_engine import SyncItem
    from app.models.sync_record import SyncItemType

    return SyncItem(
        item_type=SyncItemType.NOTEBOOK,
        item_id="nb-123",
        content_hash="notebook-hash-456",
        data={
            "notebook_uuid": "nb-123",
            "title": "Test Notebook",
            "full_path": "Work/Projects/Client A",
            "pages": [
                {"page_number": 1, "text": "Page 1 content"},
                {"page_number": 2, "text": "Page 2 content"},
            ],
            "last_opened_at": "2026-01-15T10:00:00",
            "last_modified_at": "2026-01-15T09:00:00",
        },
        source_table="notebooks",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )


@pytest.fixture
def sample_page_text_sync_item():
    """Sample SyncItem for page text syncing."""
    from app.core.sync_engine import SyncItem
    from app.models.sync_record import SyncItemType

    return SyncItem(
        item_type=SyncItemType.PAGE_TEXT,
        item_id="page-text-123",
        content_hash="page-hash-789",
        data={
            "text": "This is the OCR text from page 1",
            "page_number": 1,
            "notebook_uuid": "nb-123",
            "notebook_name": "Test Notebook",
            "existing_block_id": None,
            "existing_notebook_page_id": None,
        },
        source_table="pages",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
