"""
Metadata sync module for two-phase sync architecture.

Phase 1 of the sync process: Upload notebook metadata and page structure
without content. This creates the notebook structure immediately so users
see their content in the dashboard right away.

Phase 2 (handled by InitialSync) uploads actual page content with OCR.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.config import Config
from app.sync.cloud_sync import CloudSync, CloudSyncError

logger = logging.getLogger(__name__)


class MetadataSync:
    """
    Syncs notebook metadata without content.

    This is Phase 1 of the two-phase sync architecture:
    - Fast: No file uploads, no OCR processing
    - Creates notebook records and page stubs immediately
    - Dashboard shows pages as "Not synced" until content is uploaded
    """

    def __init__(self, config: Config, cloud_sync: CloudSync):
        """
        Initialize metadata sync.

        Args:
            config: Agent configuration
            cloud_sync: Cloud sync client for API calls
        """
        self.config = config
        self.cloud_sync = cloud_sync
        self.remarkable_folder = Path(config.remarkable.source_directory)

    async def run(self, selected_uuids: Optional[list[str]] = None) -> dict:
        """
        Sync notebook metadata and page structure to the backend.

        This scans local notebooks, extracts metadata and page UUIDs,
        and sends them to the backend in a single API call.

        Args:
            selected_uuids: Optional list of notebook UUIDs to sync (None = all)

        Returns:
            Response from the backend with sync statistics:
            {
                "success": bool,
                "notebooks_created": int,
                "notebooks_updated": int,
                "pages_registered": int,
                "pages_already_synced": int,
                "message": str
            }
        """
        logger.info("Starting metadata sync...")
        print("\n  📋 Phase 1: Syncing notebook metadata...")

        # Scan for notebooks
        notebooks_data = self._scan_notebooks(selected_uuids)

        if not notebooks_data:
            print("  ⚠️  No notebooks found to sync metadata")
            return {
                "success": True,
                "notebooks_created": 0,
                "notebooks_updated": 0,
                "pages_registered": 0,
                "pages_already_synced": 0,
                "message": "No notebooks found",
            }

        total_pages = sum(len(nb.get("pages", [])) for nb in notebooks_data)
        print(f"  Found {len(notebooks_data)} notebook(s) with {total_pages} page(s)")

        # Build and send request
        try:
            await self.cloud_sync.ensure_authenticated()

            response = await self.cloud_sync.client.post(
                f"{self.config.api.url}/sync/metadata",
                json={"notebooks": notebooks_data},
                headers=self.cloud_sync._get_headers(),
            )

            response.raise_for_status()
            result = response.json()

            # Report results
            created = result.get("notebooks_created", 0)
            updated = result.get("notebooks_updated", 0)
            pages_new = result.get("pages_registered", 0)
            pages_existing = result.get("pages_already_synced", 0)

            print(f"  ✓ Created {created} notebook(s), updated {updated}")
            print(f"  ✓ Registered {pages_new} new page(s), {pages_existing} already synced")

            logger.info(
                f"Metadata sync completed: {created} created, {updated} updated, "
                f"{pages_new} new pages, {pages_existing} existing pages"
            )

            return result

        except Exception as e:
            logger.error(f"Metadata sync failed: {e}", exc_info=True)
            print(f"  ❌ Metadata sync failed: {e}")
            raise CloudSyncError(f"Metadata sync failed: {e}")

    def _scan_notebooks(self, selected_uuids: Optional[list[str]] = None) -> list[dict]:
        """
        Scan reMarkable folder and build notebook metadata list.

        Args:
            selected_uuids: Optional list of notebook UUIDs to include (None = all)

        Returns:
            List of notebook metadata dictionaries matching backend schema
        """
        notebooks_data = []

        # Find all .metadata files
        metadata_files = list(self.remarkable_folder.glob("*.metadata"))
        logger.debug(f"Found {len(metadata_files)} .metadata files")

        for metadata_file in metadata_files:
            try:
                notebook_data = self._parse_notebook_metadata(metadata_file)

                if notebook_data is None:
                    continue  # Skip non-notebooks (folders, PDFs, etc.)

                # Filter by selection if provided
                if selected_uuids is not None and notebook_data["uuid"] not in selected_uuids:
                    continue

                notebooks_data.append(notebook_data)

            except Exception as e:
                logger.warning(f"Failed to parse {metadata_file.name}: {e}")

        return notebooks_data

    def _parse_notebook_metadata(self, metadata_file: Path) -> Optional[dict]:
        """
        Parse a .metadata file and extract full notebook metadata.

        Args:
            metadata_file: Path to the .metadata file

        Returns:
            Dictionary with notebook metadata or None if not a notebook
        """
        try:
            with open(metadata_file) as f:
                data = json.load(f)

            uuid = metadata_file.stem
            doc_type = data.get("type", "DocumentType")

            # Skip folders
            if doc_type == "CollectionType":
                return None

            # Skip PDFs and EPUBs
            pdf_file = metadata_file.with_suffix(".pdf")
            epub_file = metadata_file.with_suffix(".epub")
            if pdf_file.exists() or epub_file.exists():
                logger.debug(f"Skipping PDF/EPUB: {data.get('visibleName', uuid)}")
                return None

            # Build notebook metadata matching backend schema
            notebook_data = {
                "uuid": uuid,
                "visible_name": data.get("visibleName", "Untitled"),
                "document_type": "notebook",  # We only process notebooks
                "pages": [],  # Will be populated from .content file
            }

            # Optional fields
            parent = data.get("parent", "")
            if parent and parent != "":
                notebook_data["parent_uuid"] = parent

            if "pinned" in data:
                notebook_data["pinned"] = data["pinned"]

            if "deleted" in data:
                notebook_data["deleted"] = data["deleted"]

            if "version" in data:
                notebook_data["version"] = data["version"]

            # Convert timestamp (milliseconds) to ISO 8601
            if "lastOpened" in data:
                try:
                    ts_ms = int(data["lastOpened"])
                    dt = datetime.fromtimestamp(ts_ms / 1000.0)
                    notebook_data["last_opened"] = dt.isoformat()
                except (ValueError, TypeError):
                    pass

            if "lastOpenedPage" in data:
                notebook_data["last_opened_page"] = data["lastOpenedPage"]

            # Get page UUIDs from .content file
            pages = self._get_page_uuids(uuid)
            notebook_data["pages"] = pages

            return notebook_data

        except Exception as e:
            logger.error(f"Error parsing {metadata_file}: {e}")
            return None

    def _get_page_uuids(self, notebook_uuid: str) -> list[str]:
        """
        Extract page UUIDs from the notebook's .content file.

        The .content file contains an ordered list of page references.
        Pages can be plain strings (UUID) or dicts with an 'id' field.

        Args:
            notebook_uuid: UUID of the notebook

        Returns:
            Ordered list of page UUIDs (oldest to newest)
        """
        content_file = self.remarkable_folder / f"{notebook_uuid}.content"

        if not content_file.exists():
            logger.debug(f"No .content file for notebook {notebook_uuid}")
            return []

        try:
            with open(content_file) as f:
                content_data = json.load(f)

            # Get pages array (try both locations for different reMarkable versions)
            pages_array = content_data.get("pages", [])
            if not pages_array and "cPages" in content_data:
                pages_array = content_data.get("cPages", {}).get("pages", [])

            # Extract page UUIDs - pages can be plain strings or dicts with 'id' field
            # Skip deleted pages (they have 'deleted': {'value': 1} or similar)
            page_uuids = []
            for page_entry in pages_array:
                if isinstance(page_entry, str):
                    page_uuids.append(page_entry)
                elif isinstance(page_entry, dict) and "id" in page_entry:
                    # Check if page is deleted
                    deleted = page_entry.get("deleted", {})
                    if isinstance(deleted, dict) and deleted.get("value"):
                        continue  # Skip deleted pages
                    page_uuids.append(page_entry["id"])

            logger.debug(f"Found {len(page_uuids)} pages in .content for {notebook_uuid}")
            return page_uuids

        except Exception as e:
            logger.warning(f"Failed to read .content file for {notebook_uuid}: {e}")
            return []
