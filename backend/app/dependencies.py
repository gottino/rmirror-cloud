"""Shared dependencies for FastAPI routes."""

from functools import lru_cache

from app.config import get_settings
from app.storage import LocalStorageService, StorageService

settings = get_settings()


@lru_cache
def get_storage_service() -> StorageService:
    """
    Get storage service instance.

    Returns local storage for development,
    can be configured to return S3 storage for production.
    """
    # For now, always use local storage
    # In production, check settings and return S3StorageService if configured
    return LocalStorageService(base_path="./storage")
