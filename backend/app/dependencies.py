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

    STORAGE_BACKEND=local forces local storage. Otherwise S3 is used when its
    credentials are set; without them local storage is only allowed in debug.
    """
    if (settings.storage_backend or "").strip().lower() == "local":
        return LocalStorageService(base_path="./storage")

    if (
        settings.s3_endpoint_url
        and settings.s3_access_key
        and settings.s3_secret_key
    ):
        return S3StorageService()

    if settings.debug:
        return LocalStorageService(base_path="./storage")

    raise RuntimeError(
        "Storage is not configured: set the S3_* settings, or STORAGE_BACKEND=local "
        "to store files on local disk."
    )
