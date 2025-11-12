"""Shared dependencies for FastAPI routes."""

from functools import lru_cache

from app.config import get_settings
from app.storage import LocalStorageService, StorageService
from app.storage.s3 import S3StorageService

settings = get_settings()


@lru_cache
def get_storage_service() -> StorageService:
    """
    Get storage service instance.

    Returns S3 storage if credentials are configured (production),
    otherwise returns local storage (development).
    """
    # Use S3/Backblaze if credentials are available
    if (
        settings.s3_endpoint_url
        and settings.s3_access_key
        and settings.s3_secret_key
    ):
        return S3StorageService()

    # Fall back to local storage for development
    return LocalStorageService(base_path="./storage")
