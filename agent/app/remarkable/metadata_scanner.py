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
    """A notebook in the reMarkable filesystem."""

    uuid: str
    name: str
    last_opened: datetime
    page_count: Optional[int] = None


class MetadataScanner:
    """Scanner for reading reMarkable notebooks and grouping them by last opened date."""

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
        Scan the reMarkable folder and get all notebooks sorted by last opened.

        Returns:
            List of notebooks sorted by last opened (newest first)
        """
        logger.info(f"Scanning reMarkable folder: {self.remarkable_folder}")

        # Clear items dict to avoid duplicates on re-scan
        self.items.clear()

        # Find all .metadata files
        metadata_files = list(self.remarkable_folder.glob("*.metadata"))
        logger.info(f"Found {len(metadata_files)} metadata files")

        # Parse all metadata files (only notebooks, skip folders and PDFs)
        notebooks = []
        for metadata_file in metadata_files:
            try:
                item = self._parse_metadata_file(metadata_file)
                if item:
                    notebooks.append(item)
                    self.items[item.uuid] = item
            except Exception as e:
                logger.warning(f"Failed to parse {metadata_file.name}: {e}")

        # Sort by last opened (newest first)
        notebooks.sort(key=lambda x: x.last_opened, reverse=True)
        logger.info(f"Found {len(notebooks)} notebooks")

        return notebooks

    def _parse_metadata_file(self, metadata_file: Path) -> Optional[NotebookItem]:
        """
        Parse a .metadata file and return notebook info.

        Args:
            metadata_file: Path to .metadata file

        Returns:
            NotebookItem or None if it's not a notebook (folder, PDF, EPUB)
        """
        try:
            with open(metadata_file, 'r') as f:
                data = json.load(f)

            uuid = metadata_file.stem
            doc_type = data.get("type", "DocumentType")

            # Skip folders entirely
            if doc_type == "CollectionType":
                return None

            # Skip PDFs and EPUBs (they have .pdf or .epub files)
            pdf_file = metadata_file.with_suffix('.pdf')
            epub_file = metadata_file.with_suffix('.epub')
            if pdf_file.exists() or epub_file.exists():
                logger.debug(f"Skipping PDF/EPUB: {data.get('visibleName', uuid)}")
                return None

            # Get lastOpened timestamp (fallback to lastModified if not available)
            last_opened_ms = int(data.get("lastOpened", data.get("lastModified", "0")))
            last_opened = datetime.fromtimestamp(last_opened_ms / 1000.0)

            # Get page count from .content file
            page_count = 0
            content_file = metadata_file.with_suffix('.content')
            if content_file.exists():
                try:
                    with open(content_file, 'r') as f:
                        content_data = json.load(f)
                        # Use PageCount property if available, otherwise count pages array
                        page_count = content_data.get("pageCount", len(content_data.get("pages", [])))
                except Exception as e:
                    logger.warning(f"Failed to read page count from {content_file.name}: {e}")
                    page_count = 0

            return NotebookItem(
                uuid=uuid,
                name=data.get("visibleName", "Untitled"),
                last_opened=last_opened,
                page_count=page_count,
            )

        except Exception as e:
            logger.error(f"Error parsing {metadata_file}: {e}")
            return None

    def _get_date_group(self, date: datetime) -> str:
        """
        Get the date group for a notebook based on its last opened date.

        Args:
            date: Last opened datetime

        Returns:
            Date group label: "Today", "Last Week", "Last Month", "Last Year", or "Older"
        """
        now = datetime.now()
        diff = now - date

        if diff.days == 0:
            return "Today"
        elif diff.days <= 7:
            return "Last Week"
        elif diff.days <= 30:
            return "Last Month"
        elif diff.days <= 365:
            return "Last Year"
        else:
            return "Older"

    def to_dict(self, items: Optional[List[NotebookItem]] = None) -> List[dict]:
        """
        Convert notebooks to grouped dictionary format for JSON serialization.

        Args:
            items: List of notebooks sorted by last opened (from scan())

        Returns:
            List of date groups with notebooks
        """
        if items is None:
            return []

        # Group notebooks by date range
        groups = {
            "Today": [],
            "Last Week": [],
            "Last Month": [],
            "Last Year": [],
            "Older": []
        }

        for item in items:
            group = self._get_date_group(item.last_opened)
            groups[group].append({
                "uuid": item.uuid,
                "name": item.name,
                "lastOpened": item.last_opened.isoformat(),
                "pageCount": item.page_count or 0,
            })

        # Build result with only non-empty groups (in order)
        result = []
        for group_name in ["Today", "Last Week", "Last Month", "Last Year", "Older"]:
            if groups[group_name]:
                result.append({
                    "group": group_name,
                    "notebooks": groups[group_name]
                })

        return result

    def get_all_document_uuids(self) -> List[str]:
        """
        Get all notebook UUIDs.

        Returns:
            List of UUIDs for all notebooks
        """
        return list(self.items.keys())

    def count_total_pages(self, selected_uuids: Optional[List[str]] = None) -> int:
        """
        Count total pages in selected notebooks.

        Args:
            selected_uuids: List of UUIDs to count pages for (None = all)

        Returns:
            Total page count
        """
        total = 0

        for uuid, item in self.items.items():
            # If selection provided, only count selected items
            if selected_uuids is not None and uuid not in selected_uuids:
                continue

            if item.page_count:
                total += item.page_count

        return total
