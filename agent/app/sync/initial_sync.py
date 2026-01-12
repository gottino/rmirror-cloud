"""
Initial sync module for uploading all notebooks when agent first starts.

This handles the case where the agent hasn't been running for a while
or is running for the first time and needs to catch up.
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import List, Optional

from app.config import Config
from app.remarkable.metadata_scanner import MetadataScanner
from app.sync.cloud_sync import CloudSync

logger = logging.getLogger(__name__)


class InitialSync:
    """Handles initial synchronization of all notebooks to the cloud."""

    def __init__(self, config: Config, cloud_sync: CloudSync):
        """
        Initialize initial sync.

        Args:
            config: Agent configuration
            cloud_sync: Cloud sync client
        """
        self.config = config
        self.cloud_sync = cloud_sync
        self.remarkable_folder = Path(config.remarkable.source_directory)

    async def run(self, selected_notebook_uuids: Optional[List[str]] = None) -> dict:
        """
        Perform initial sync of all notebooks.

        Uploads all .rm files and .content files for selected notebooks.
        This ensures the backend has the complete state of all notebooks.

        Args:
            selected_notebook_uuids: List of notebook UUIDs to sync (None = all)

        Returns:
            Statistics dictionary with sync results
        """
        logger.info("Starting initial sync...")
        print("\n" + "=" * 70)
        print("  📚 Initial Sync - Uploading Notebooks")
        print("=" * 70)
        print()

        # Scan for notebooks
        scanner = MetadataScanner(self.remarkable_folder)
        notebooks = scanner.scan()

        # Filter by selection
        if selected_notebook_uuids is not None:
            notebooks = [nb for nb in notebooks if nb.uuid in selected_notebook_uuids]

        if not notebooks:
            print("⚠️  No notebooks to sync")
            return {"notebooks": 0, "pages": 0, "failed": 0}

        print(f"Found {len(notebooks)} notebook(s) to sync")
        print()

        stats = {
            "notebooks": 0,
            "pages": 0,
            "failed": 0,
        }

        # Sync each notebook
        for i, notebook in enumerate(notebooks, 1):
            try:
                print(f"[{i}/{len(notebooks)}] {notebook.name}")
                print(f"   UUID: {notebook.uuid}")
                print(f"   Pages: {notebook.page_count or 0}")

                nb_stats = await self._sync_notebook(notebook.uuid)
                stats["notebooks"] += 1
                stats["pages"] += nb_stats["uploaded"]
                stats["failed"] += nb_stats["failed"]

                print()

            except Exception as e:
                logger.error(f"Failed to sync notebook {notebook.uuid}: {e}", exc_info=True)
                print(f"   ❌ Failed: {e}")
                print()
                stats["failed"] += 1

        print("=" * 70)
        print(f"  ✅ Initial Sync Complete")
        print(f"     Notebooks: {stats['notebooks']}")
        print(f"     Pages: {stats['pages']}")
        if stats['failed'] > 0:
            print(f"     Failed: {stats['failed']}")
        print("=" * 70)
        print()

        return stats

    async def _sync_notebook(self, notebook_uuid: str) -> dict:
        """
        Sync a single notebook.

        Uploads pages (.rm files) in order from newest to oldest (based on .content file),
        respects max_pages_per_notebook config, then uploads .content file for mapping.

        Args:
            notebook_uuid: UUID of the notebook

        Returns:
            Statistics dictionary
        """
        notebook_dir = self.remarkable_folder / notebook_uuid

        # Check if notebook directory exists
        if not notebook_dir.exists() or not notebook_dir.is_dir():
            logger.warning(f"Notebook directory not found: {notebook_dir}")
            return {"uploaded": 0, "failed": 0, "skipped": 0}

        stats = {
            "uploaded": 0,
            "failed": 0,
            "skipped": 0,
            "failed_pages": [],  # Track which pages failed
        }

        # 1. Get all page files
        all_page_files = list(notebook_dir.glob("*.rm"))

        if not all_page_files:
            logger.info(f"No pages found in notebook {notebook_uuid}")
            return {"uploaded": 0, "failed": 0, "skipped": 0}

        # 2. Read .content file to get authoritative page order
        # In reMarkable's .content file, pages array is ordered oldest to newest
        content_file = self.remarkable_folder / f"{notebook_uuid}.content"
        page_order = []  # List of page UUIDs in order (oldest to newest)

        if content_file.exists():
            try:
                with open(content_file, 'r') as f:
                    content_data = json.load(f)

                # Get pages array (try both locations for different reMarkable versions)
                pages_array = content_data.get("pages", [])
                if not pages_array and "cPages" in content_data:
                    pages_array = content_data.get("cPages", {}).get("pages", [])

                page_order = pages_array
                logger.debug(f"Found {len(page_order)} pages in .content file for {notebook_uuid}")

            except Exception as e:
                logger.warning(f"Failed to read .content file for {notebook_uuid}: {e}")

        # 3. Create UUID to file mapping
        page_file_map = {pf.stem: pf for pf in all_page_files}

        # 4. Sort page files: newest first (reverse of .content order)
        # This ensures newest pages are uploaded first and get OCR priority
        if page_order:
            # Build ordered list from .content (reversed = newest first)
            ordered_page_files = []
            for uuid in reversed(page_order):
                if uuid in page_file_map:
                    ordered_page_files.append(page_file_map[uuid])

            # Add any orphaned pages (in .rm folder but not in .content) at the end
            orphaned_uuids = set(page_file_map.keys()) - set(page_order)
            if orphaned_uuids:
                logger.warning(f"Found {len(orphaned_uuids)} orphaned pages not in .content file")
                for uuid in orphaned_uuids:
                    ordered_page_files.append(page_file_map[uuid])
        else:
            # No .content file or empty - fall back to file modification time (newest first)
            logger.warning(f"No page order from .content, falling back to file mtime")
            ordered_page_files = sorted(
                all_page_files,
                key=lambda p: p.stat().st_mtime,
                reverse=True  # Newest first
            )

        # 5. Apply page limit (take from front = newest pages)
        max_pages = self.config.sync.max_pages_per_notebook
        if max_pages is not None and max_pages > 0 and len(ordered_page_files) > max_pages:
            skipped_count = len(ordered_page_files) - max_pages
            page_files_to_upload = ordered_page_files[:max_pages]  # Take first N (newest)
            stats["skipped"] = skipped_count
            print(f"   ⚡ Limiting to {max_pages} most recent pages (skipping {skipped_count} older pages)")
            logger.info(f"Limited notebook {notebook_uuid} to {max_pages} newest pages")
        else:
            page_files_to_upload = ordered_page_files

        # 6. Upload pages in order (newest first)
        if page_files_to_upload:
            print(f"   📤 Uploading {len(page_files_to_upload)} page(s) (newest first)...")

            for page_file in page_files_to_upload:
                try:
                    await self.cloud_sync.upload_file(page_file, notebook_uuid, "rm")
                    stats["uploaded"] += 1
                except Exception as e:
                    logger.error(f"Failed to upload {page_file.name}: {e}")
                    stats["failed"] += 1
                    stats["failed_pages"].append(page_file.stem)

        # 7. Upload .content file to establish page ordering in backend
        if content_file.exists():
            try:
                print(f"   📋 Uploading .content file...")
                result = await self.cloud_sync.upload_file(content_file, notebook_uuid, "content")

                # Check if it was skipped (notebook doesn't exist yet)
                if result.get("skipped"):
                    logger.debug(f"Content file skipped: {result.get('reason')}")
                else:
                    pages_mapped = result.get("pages_mapped", 0)
                    if pages_mapped > 0:
                        print(f"   ✓ Mapped {pages_mapped} pages")

            except Exception as e:
                logger.error(f"Failed to upload content file: {e}")
                stats["failed"] += 1

        # 8. Report results
        if stats["failed"] > 0:
            print(f"   ⚠️  {stats['failed']} page(s) failed to upload")
            if stats["failed_pages"]:
                logger.warning(f"Failed pages: {stats['failed_pages'][:5]}{'...' if len(stats['failed_pages']) > 5 else ''}")

        print(f"   ✓ Uploaded {stats['uploaded']} page(s)")

        return stats


async def perform_initial_sync_if_needed(config: Config, cloud_sync: CloudSync) -> bool:
    """
    Check if initial sync is needed and perform it.

    This is called when the agent starts. It checks if there are notebooks
    that haven't been synced yet and uploads them.

    Args:
        config: Agent configuration
        cloud_sync: Cloud sync client

    Returns:
        True if initial sync was performed, False if skipped
    """
    # For now, we'll always skip initial sync unless explicitly requested
    # Later, we could add logic to check the backend for missing notebooks
    # and only sync those that are missing

    # TODO: Add logic to query backend and compare with local notebooks
    # For now, users will need to manually trigger initial sync via the web UI

    logger.info("Skipping automatic initial sync (use web UI to trigger)")
    return False
