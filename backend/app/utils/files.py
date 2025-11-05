"""File handling utilities."""

import hashlib
from typing import BinaryIO

from fastapi import HTTPException, UploadFile, status


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
