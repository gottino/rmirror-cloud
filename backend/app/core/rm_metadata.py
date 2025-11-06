"""Parse reMarkable .metadata files.

reMarkable stores notebook metadata in JSON format in .metadata files.
These contain visible name, last modified time, document type, etc.
"""

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, BinaryIO


@dataclass
class RMMetadata:
    """Metadata for a reMarkable notebook."""

    visible_name: str
    document_type: str  # "DocumentType" or "CollectionType"
    parent: str  # UUID of parent folder
    last_modified: datetime
    version: int
    pinned: bool = False
    synced: bool = False
    modified_client: str | None = None
    current_page: int | None = None
    bookmarked: bool = False
    redirect_document_uuid: str | None = None


class RMMetadataParser:
    """Parser for reMarkable .metadata files."""

    def parse(self, file: BinaryIO) -> RMMetadata:
        """
        Parse a .metadata file.

        Args:
            file: File object or bytes containing JSON metadata

        Returns:
            Parsed RMMetadata object

        Raises:
            ValueError: If metadata format is invalid
        """
        try:
            data = json.load(file)
            return self._parse_dict(data)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in .metadata file: {e}")

    def parse_string(self, json_str: str) -> RMMetadata:
        """
        Parse metadata from JSON string.

        Args:
            json_str: JSON string

        Returns:
            Parsed RMMetadata object
        """
        data = json.loads(json_str)
        return self._parse_dict(data)

    def _parse_dict(self, data: dict[str, Any]) -> RMMetadata:
        """Parse metadata from dictionary."""
        # Required fields
        if "visibleName" not in data:
            raise ValueError("Missing required field: visibleName")

        # Parse last modified timestamp (milliseconds since epoch)
        last_modified_ms = data.get("lastModified", "0")
        last_modified = datetime.fromtimestamp(int(last_modified_ms) / 1000.0)

        # Determine document type
        doc_type = data.get("type", "DocumentType")

        return RMMetadata(
            visible_name=data["visibleName"],
            document_type=doc_type,
            parent=data.get("parent", ""),
            last_modified=last_modified,
            version=data.get("version", 0),
            pinned=data.get("pinned", False),
            synced=data.get("synced", False),
            modified_client=data.get("lastModifiedClient"),
            current_page=data.get("currentPage"),
            bookmarked=data.get("bookmarked", False),
            redirect_document_uuid=data.get("redirectionPageMap"),
        )

    def to_dict(self, metadata: RMMetadata) -> dict[str, Any]:
        """
        Convert RMMetadata back to dictionary format.

        Args:
            metadata: RMMetadata object

        Returns:
            Dictionary in reMarkable format
        """
        result = {
            "visibleName": metadata.visible_name,
            "type": metadata.document_type,
            "parent": metadata.parent,
            "lastModified": str(int(metadata.last_modified.timestamp() * 1000)),
            "version": metadata.version,
            "pinned": metadata.pinned,
            "synced": metadata.synced,
        }

        if metadata.modified_client:
            result["lastModifiedClient"] = metadata.modified_client
        if metadata.current_page is not None:
            result["currentPage"] = metadata.current_page
        if metadata.bookmarked:
            result["bookmarked"] = metadata.bookmarked
        if metadata.redirect_document_uuid:
            result["redirectionPageMap"] = metadata.redirect_document_uuid

        return result
