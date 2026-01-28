"""File handling utilities."""

import hashlib
import logging
from typing import BinaryIO, Optional

from fastapi import HTTPException, UploadFile, status

logger = logging.getLogger(__name__)

# Try to import python-magic for MIME type detection
# Falls back gracefully if libmagic is not installed
try:
    import magic
    MAGIC_AVAILABLE = True
except ImportError:
    MAGIC_AVAILABLE = False
    logger.warning(
        "python-magic not available (libmagic not installed). "
        "MIME type validation will be skipped."
    )


def calculate_file_hash(file: BinaryIO) -> str:
    """
    Calculate SHA256 hash of a file.

    Args:
        file: File object

    Returns:
        Hexadecimal hash string
    """
    sha256_hash = hashlib.sha256()

    # Read file in chunks to handle large files
    file.seek(0)
    for chunk in iter(lambda: file.read(8192), b""):
        sha256_hash.update(chunk)

    file.seek(0)  # Reset file pointer
    return sha256_hash.hexdigest()


def validate_file_type(file: UploadFile, allowed_extensions: list[str]) -> str:
    """
    Validate file type based on extension.

    Args:
        file: Uploaded file
        allowed_extensions: List of allowed extensions (e.g., ['.pdf', '.epub'])

    Returns:
        File extension

    Raises:
        HTTPException: If file type is not allowed
    """
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename is required",
        )

    # Get extension
    extension = None
    if "." in file.filename:
        extension = "." + file.filename.rsplit(".", 1)[1].lower()

    if extension not in allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type not allowed. Allowed types: {', '.join(allowed_extensions)}",
        )

    return extension


def get_document_type(extension: str) -> str:
    """
    Map file extension to document type.

    Args:
        extension: File extension (e.g., '.pdf')

    Returns:
        Document type string
    """
    mapping = {
        ".pdf": "pdf",
        ".epub": "epub",
    }
    return mapping.get(extension.lower(), "notebook")


# MIME type to extension mapping for validation
MIME_TYPE_MAP = {
    "application/pdf": [".pdf"],
    "application/epub+zip": [".epub"],
    "application/octet-stream": [".rm", ".metadata", ".content"],  # Binary files
    "text/plain": [".metadata", ".content"],  # Some metadata files are text
    "application/json": [".metadata", ".content"],  # JSON metadata
}


def validate_mime_type(
    file_content: bytes,
    expected_extensions: list[str],
    filename: Optional[str] = None,
) -> str:
    """
    Validate file content MIME type matches expected extensions.

    Uses python-magic to detect actual file content type, preventing
    attackers from bypassing extension checks by renaming files.

    Args:
        file_content: Raw file bytes (at least first 2048 bytes)
        expected_extensions: List of allowed extensions
        filename: Optional filename for logging

    Returns:
        Detected MIME type

    Raises:
        HTTPException: If MIME type doesn't match expected extensions
    """
    # If magic is not available, skip MIME validation
    if not MAGIC_AVAILABLE:
        return "application/octet-stream"

    try:
        # Detect MIME type from file content
        detected_mime = magic.from_buffer(file_content, mime=True)
    except Exception as e:
        logger.warning(f"MIME detection failed for {filename}: {e}")
        # Allow through if detection fails - don't break functionality
        return "application/octet-stream"

    # Build list of allowed MIME types for expected extensions
    allowed_mimes = set()
    for ext in expected_extensions:
        for mime, exts in MIME_TYPE_MAP.items():
            if ext.lower() in exts:
                allowed_mimes.add(mime)

    # Also allow application/octet-stream for binary files (common fallback)
    allowed_mimes.add("application/octet-stream")

    if detected_mime not in allowed_mimes:
        logger.warning(
            f"MIME type mismatch for {filename}: "
            f"detected={detected_mime}, allowed={allowed_mimes}"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File content does not match expected type",
        )

    return detected_mime


async def validate_upload_file(
    file: UploadFile,
    allowed_extensions: list[str],
    max_size_bytes: Optional[int] = None,
) -> tuple[str, bytes]:
    """
    Comprehensive file upload validation.

    Validates:
    1. Filename exists and has allowed extension
    2. File size within limits (if specified)
    3. MIME type matches extension (content validation)

    Args:
        file: Uploaded file
        allowed_extensions: List of allowed extensions
        max_size_bytes: Optional maximum file size

    Returns:
        Tuple of (extension, file_content)

    Raises:
        HTTPException: If validation fails
    """
    # Validate extension
    extension = validate_file_type(file, allowed_extensions)

    # Read file content
    content = await file.read()
    await file.seek(0)  # Reset for potential re-reading

    # Validate file size
    if max_size_bytes and len(content) > max_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File too large. Maximum size: {max_size_bytes / (1024*1024):.1f}MB",
        )

    # Validate MIME type (use first 2048 bytes for detection)
    validate_mime_type(content[:2048], allowed_extensions, file.filename)

    return extension, content
