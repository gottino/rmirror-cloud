"""Test configuration and fixtures for pytest.

Provides fixtures for:
- In-memory SQLite database
- Test users with quota states
- Rate limiter reset
- Test data factories
"""

from datetime import datetime, timedelta, timezone
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
