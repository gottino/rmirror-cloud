"""Service functions for Obsidian sync integration."""

import hashlib
import secrets
from typing import Optional


def generate_api_key() -> str:
    """Generate a URL-safe API key for Obsidian plugin authentication."""
    return secrets.token_urlsafe(32)


def hash_api_key(api_key: str) -> str:
    """Hash an API key using SHA256 for storage."""
    return hashlib.sha256(api_key.encode()).hexdigest()


def compute_notebook_content_hash(
    pages: list[tuple[int, str]],
) -> Optional[str]:
    """
    Compute composite content hash for a notebook's OCR'd pages.

    Args:
        pages: List of (page_number, ocr_text) tuples, ordered by page_number.

    Returns:
        SHA256 hex digest, or None if no pages.
    """
    if not pages:
        return None
    hash_input = "".join(f"{page_number}:{ocr_text}" for page_number, ocr_text in pages)
    return hashlib.sha256(hash_input.encode()).hexdigest()
