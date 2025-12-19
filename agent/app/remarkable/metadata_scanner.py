"""
Metadata scanner for building reMarkable folder structure.

Scans the reMarkable Desktop folder and builds a tree structure
from .metadata files to allow users to select which notebooks to sync.
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class NotebookItem:
    """A notebook or folder in the reMarkable filesystem."""

    uuid: str
    name: str
    type: str  # "CollectionType" (folder) or "DocumentType" (notebook/PDF)
    parent: str  # UUID of parent folder, or "" for root
    last_modified: datetime
    children: List['NotebookItem']  # For folders
    page_count: Optional[int] = None  # For notebooks


class MetadataScanner:
    """Scanner for building folder structure from reMarkable metadata files."""

    def __init__(self, remarkable_folder: Path):
        """
        Initialize the scanner.

        Args:
            remarkable_folder: Path to reMarkable Desktop sync folder
        """
        self.remarkable_folder = Path(remarkable_folder)
        self.items: Dict[str, NotebookItem] = {}  # uuid -> NotebookItem

    def scan(self) -> List[NotebookItem]:
        """
        Scan the reMarkable folder and build the folder tree.

        Returns:
            List of root-level items (folders and notebooks with no parent)
        """
        logger.info(f"Scanning reMarkable folder: {self.remarkable_folder}")

        # Clear items dict to avoid duplicates on re-scan
        self.items.clear()

        # Find all .metadata files
        metadata_files = list(self.remarkable_folder.glob("*.metadata"))
        logger.info(f"Found {len(metadata_files)} metadata files")

        # Parse all metadata files first
        for metadata_file in metadata_files:
            try:
                item = self._parse_metadata_file(metadata_file)
                if item:
                    if item.uuid in self.items:
                        logger.warning(f"Duplicate UUID found: {item.uuid} ({item.name})")
                    self.items[item.uuid] = item
            except Exception as e:
                logger.warning(f"Failed to parse {metadata_file.name}: {e}")

        # Build the tree structure
        tree = self._build_tree()
        logger.info(f"Built tree with {len(tree)} root items")

        return tree

    def _parse_metadata_file(self, metadata_file: Path) -> Optional[NotebookItem]:
        """
        Parse a .metadata file.

        Args:
            metadata_file: Path to .metadata file

        Returns:
            NotebookItem or None if parsing failed or if it's a PDF/EPUB
        """
        try:
            with open(metadata_file, 'r') as f:
                data = json.load(f)

            uuid = metadata_file.stem  # filename without .metadata extension
            doc_type = data.get("type", "DocumentType")

            # Skip folders - we'll handle them separately
            if doc_type == "CollectionType":
                return NotebookItem(
                    uuid=uuid,
                    name=data.get("visibleName", "Untitled"),
                    type=doc_type,
                    parent=data.get("parent", ""),
                    last_modified=datetime.fromtimestamp(int(data.get("lastModified", "0")) / 1000.0),
                    children=[],
                    page_count=None,
                )

            # For DocumentType, check if it's a notebook (not PDF/EPUB)
            # PDFs have .pdf files, EPUBs have .epub files, notebooks have folders with .rm files
            pdf_file = metadata_file.with_suffix('.pdf')
            epub_file = metadata_file.with_suffix('.epub')

            # Skip if PDF or EPUB exists
            if pdf_file.exists() or epub_file.exists():
                logger.debug(f"Skipping PDF/EPUB: {data.get('visibleName', uuid)}")
                return None

            # Get page count for notebooks only
            page_count = None
            content_file = metadata_file.with_suffix('.content')
            if content_file.exists():
                try:
                    with open(content_file, 'r') as f:
                        content_data = json.load(f)
                        pages = content_data.get("pages", [])
                        page_count = len(pages) if pages else None
                except Exception:
                    pass

            return NotebookItem(
                uuid=uuid,
                name=data.get("visibleName", "Untitled"),
                type=doc_type,
                parent=data.get("parent", ""),
                last_modified=datetime.fromtimestamp(int(data.get("lastModified", "0")) / 1000.0),
                children=[],
                page_count=page_count,
            )

        except Exception as e:
            logger.error(f"Error parsing {metadata_file}: {e}")
            return None

    def _build_tree(self) -> List[NotebookItem]:
        """
        Build the tree structure by organizing items by parent-child relationships.

        Returns:
            List of root-level items
        """
        root_items = []

        # First pass: organize children under parents
        for item in self.items.values():
            if item.parent == "" or item.parent == "trash":
                # Root level item
                root_items.append(item)
                logger.debug(f"Added root item: {item.name} ({item.uuid})")
            elif item.parent in self.items:
                # Add as child to parent
                parent = self.items[item.parent]
                parent.children.append(item)
                logger.debug(f"Added {item.name} as child of {parent.name}")
            else:
                # Parent not found - treat as root level
                logger.warning(
                    f"Parent {item.parent} not found for {item.name} ({item.uuid}), "
                    f"treating as root level"
                )
                root_items.append(item)

        # Sort root items by name
        root_items.sort(key=lambda x: x.name.lower())

        # Recursively sort children
        def sort_children(item: NotebookItem):
            # Sort folders first, then notebooks
            item.children.sort(key=lambda x: (x.type != "CollectionType", x.name.lower()))
            for child in item.children:
                sort_children(child)

        for item in root_items:
            sort_children(item)

        return root_items

    def to_dict(self, items: Optional[List[NotebookItem]] = None) -> List[dict]:
        """
        Convert tree structure to dictionary format for JSON serialization.

        Args:
            items: List of items to convert (defaults to root items)

        Returns:
            List of dictionaries representing the tree
        """
        if items is None:
            items = self._build_tree()

        def item_to_dict(item: NotebookItem) -> dict:
            result = {
                "uuid": item.uuid,
                "name": item.name,
                "type": item.type,
                "lastModified": item.last_modified.isoformat(),
            }

            if item.page_count is not None:
                result["pageCount"] = item.page_count

            if item.children:
                result["children"] = [item_to_dict(child) for child in item.children]

            return result

        return [item_to_dict(item) for item in items]

    def get_all_document_uuids(self) -> List[str]:
        """
        Get all document UUIDs (not folders).

        Returns:
            List of UUIDs for all notebooks/PDFs/EPUBs
        """
        uuids = []
        for item in self.items.values():
            if item.type == "DocumentType":
                uuids.append(item.uuid)
        return uuids

    def count_total_pages(self, selected_uuids: Optional[List[str]] = None) -> int:
        """
        Count total pages in selected notebooks.

        Args:
            selected_uuids: List of UUIDs to count pages for (None = all)

        Returns:
            Total page count
        """
        total = 0

        for item in self.items.values():
            # Only count documents (not folders)
            if item.type != "DocumentType":
                continue

            # If selection provided, only count selected items
            if selected_uuids is not None and item.uuid not in selected_uuids:
                continue

            if item.page_count:
                total += item.page_count

        return total
