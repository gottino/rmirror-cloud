"""Content fingerprinting utilities for sync deduplication.

Generates hashes and signatures for content to detect changes and prevent duplicates.
"""

import hashlib
from typing import Optional


def generate_content_hash(content: str) -> str:
    """
    Generate SHA-256 hash of content.

    Used for exact content matching and change detection.

    Args:
        content: Text content to hash

    Returns:
        Hex-encoded SHA-256 hash (64 characters)

    Example:
        >>> hash1 = generate_content_hash("Buy milk")
        >>> hash2 = generate_content_hash("Buy milk")
        >>> hash1 == hash2
        True
    """
    return hashlib.sha256(content.strip().encode()).hexdigest()


def fingerprint_page(
    notebook_uuid: str,
    page_number: int,
    ocr_text: str,
    page_uuid: Optional[str] = None
) -> str:
    """
    Generate content hash for a page.

    Includes notebook context to ensure uniqueness across notebooks.

    Args:
        notebook_uuid: UUID of the notebook
        page_number: Page number in notebook
        ocr_text: OCR-extracted text content
        page_uuid: Optional reMarkable page UUID

    Returns:
        SHA-256 hash of page content with context

    Example:
        >>> hash = fingerprint_page(
        ...     notebook_uuid="abc-123",
        ...     page_number=5,
        ...     ocr_text="Meeting notes..."
        ... )
    """
    # Include page UUID if available for better tracking
    if page_uuid:
        content = f"{notebook_uuid}:{page_number}:{page_uuid}:{ocr_text.strip()}"
    else:
        content = f"{notebook_uuid}:{page_number}:{ocr_text.strip()}"

    return generate_content_hash(content)


def fingerprint_todo(
    todo_text: str,
    completed: bool,
    notebook_uuid: Optional[str],
    page_number: Optional[int] = None,
) -> str:
    """Content hash of what a todo target shows for a todo.

    Covers the exact text and the completed state, so an edited text or a
    newly checked box gives a new hash and the todo is synced again, plus the
    notebook and page it came from (shown in the task's description).
    De-duplication itself is per todo and target (``sync_records.item_id``),
    so two todos with the same text never hide each other.

    Example:
        >>> fingerprint_todo("Buy milk", False, "abc-123", 5) != fingerprint_todo(
        ...     "Buy milk", True, "abc-123", 5)
        True
    """
    content = "|".join(
        [
            f"text:{(todo_text or '').strip()}",
            f"completed:{1 if completed else 0}",
            f"notebook:{notebook_uuid or ''}",
            f"page:{'' if page_number is None else page_number}",
        ]
    )
    return generate_content_hash(content)
