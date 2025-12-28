"""Content fingerprinting utilities for sync deduplication.

Generates hashes and signatures for content to detect changes and prevent duplicates.
"""

import hashlib
import re
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


def generate_fuzzy_signature(text: str) -> str:
    """
    Generate fuzzy signature for approximate matching.

    Creates a normalized representation of text that's resilient to:
    - Case changes
    - Punctuation variations
    - Word order changes (sorted alphabetically)

    Useful for detecting duplicate todos despite OCR variations.

    Args:
        text: Text to generate signature for

    Returns:
        Fuzzy signature (lowercase, no punctuation, sorted words joined by '_')

    Example:
        >>> sig1 = generate_fuzzy_signature("Buy milk!")
        >>> sig2 = generate_fuzzy_signature("buy MILK")
        >>> sig3 = generate_fuzzy_signature("MILK buy")
        >>> sig1 == sig2 == sig3
        True
    """
    # Lowercase
    text_lower = text.lower()

    # Remove punctuation and extra whitespace
    text_clean = re.sub(r'[^\w\s]', '', text_lower)

    # Split into words and sort
    words = text_clean.split()
    words_sorted = sorted(words)

    # Join with underscore
    return '_'.join(words_sorted)


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
    notebook_uuid: str,
    page_number: Optional[int] = None
) -> tuple[str, str]:
    """
    Generate both content hash and fuzzy signature for a todo.

    Returns both exact hash (for strict matching) and fuzzy signature
    (for detecting OCR variations).

    Args:
        todo_text: Todo text content
        notebook_uuid: UUID of notebook containing the todo
        page_number: Optional page number

    Returns:
        Tuple of (content_hash, fuzzy_signature)

    Example:
        >>> hash, fuzzy = fingerprint_todo(
        ...     todo_text="Buy milk!",
        ...     notebook_uuid="abc-123",
        ...     page_number=5
        ... )
        >>> fuzzy
        'buy_milk'
    """
    # Generate fuzzy signature
    fuzzy_sig = generate_fuzzy_signature(todo_text)

    # Generate content hash including context
    if page_number is not None:
        content = f"{fuzzy_sig}:{notebook_uuid}:{page_number}"
    else:
        content = f"{fuzzy_sig}:{notebook_uuid}"

    content_hash = generate_content_hash(content)

    return content_hash, fuzzy_sig


def fingerprint_highlight(
    original_text: str,
    corrected_text: str,
    source_file: str,
    page_num: int
) -> str:
    """
    Generate content hash for a highlight.

    Includes both original and corrected text, plus location context.

    Args:
        original_text: Original highlighted text
        corrected_text: User-corrected text (if any)
        source_file: Source file path or identifier
        page_num: Page number

    Returns:
        SHA-256 hash of highlight with context

    Example:
        >>> hash = fingerprint_highlight(
        ...     original_text="handwritten text",
        ...     corrected_text="corrected version",
        ...     source_file="notebook.pdf",
        ...     page_num=3
        ... )
    """
    content = f"{original_text}:{corrected_text}:{source_file}:{page_num}"
    return generate_content_hash(content)


def fingerprint_notebook_metadata(
    notebook_uuid: str,
    title: str,
    folder_path: Optional[str] = None
) -> str:
    """
    Generate content hash for notebook metadata.

    Used to detect title changes or structure changes.

    Args:
        notebook_uuid: UUID of the notebook
        title: Notebook title
        folder_path: Optional folder path

    Returns:
        SHA-256 hash of notebook metadata

    Example:
        >>> hash = fingerprint_notebook_metadata(
        ...     notebook_uuid="abc-123",
        ...     title="Meeting Notes",
        ...     folder_path="/Work/2025"
        ... )
    """
    if folder_path:
        content = f"{notebook_uuid}:{title}:{folder_path}"
    else:
        content = f"{notebook_uuid}:{title}"

    return generate_content_hash(content)
