"""
Initial sync module for uploading all notebooks when agent first starts.

This implements a two-phase sync architecture:
- Phase 1 (Metadata): Fast sync of notebook structure and page UUIDs
- Phase 2 (Content): Slower upload of .rm files with OCR processing

This approach ensures users see their notebooks immediately in the dashboard,
while content syncs in the background with proper rate limit handling.
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import List, Optional

from app.config import Config
from app.remarkable.metadata_scanner import MetadataScanner
from app.sync.cloud_sync import CloudSync, CloudSyncError, QuotaExceededError, RateLimitError
from app.sync.metadata_sync import MetadataSync

logger = logging.getLogger(__name__)


class InitialSync:
    """
    Handles initial synchronization of all notebooks to the cloud.

    Uses a two-phase approach:
    1. Metadata sync (fast): Creates notebook structure immediately
    2. Content sync (slow): Uploads pages with rate limit handling
    """

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
        self.metadata_sync = MetadataSync(config, cloud_sync)

    async def run(self, selected_notebook_uuids: Optional[List[str]] = None) -> dict:
        """
        Perform initial sync of all notebooks using two-phase approach.

        Phase 1: Sync metadata (fast) - notebooks appear in dashboard immediately
        Phase 2: Sync content (slow) - upload .rm files with rate limit handling

        Args:
            selected_notebook_uuids: List of notebook UUIDs to sync (None = all)

        Returns:
            Statistics dictionary with sync results
        """
        logger.info("Starting initial sync (two-phase)...")
        print("\n" + "=" * 70)
        print("  📚 Initial Sync - Two-Phase Upload")
        print("=" * 70)

        # ================================================================
        # PHASE 1: Metadata Sync (Fast)
        # ================================================================
        try:
            metadata_result = await self.metadata_sync.run(selected_notebook_uuids)
            phase1_success = metadata_result.get("success", False)
        except Exception as e:
            logger.error(f"Phase 1 (metadata sync) failed: {e}", exc_info=True)
            print(f"\n  ❌ Phase 1 failed: {e}")
            print("     Continuing with Phase 2 (content sync)...")
            phase1_success = False
            metadata_result = {}

        # ================================================================
        # PHASE 2: Content Sync (Slow, with rate limiting)
        # ================================================================
        print("\n  📤 Phase 2: Uploading page content...")

        # Scan for notebooks
        scanner = MetadataScanner(self.remarkable_folder)
        notebooks = scanner.scan()

        # Filter by selection
        if selected_notebook_uuids is not None:
            notebooks = [nb for nb in notebooks if nb.uuid in selected_notebook_uuids]

        if not notebooks:
            print("  ⚠️  No notebooks to sync")
            return {
                "notebooks": 0,
                "pages": 0,
                "failed": 0,
                "rate_limited": 0,
                "phase1": metadata_result,
            }

        print(f"  Found {len(notebooks)} notebook(s) for content sync")
        print()

        stats = {
            "notebooks": 0,
            "pages": 0,
            "failed": 0,
            "skipped": 0,
            "rate_limited": 0,
        }

        # Track if we hit rate limits to show summary message
        rate_limit_hit = False

        # Sync each notebook's content
        for i, notebook in enumerate(notebooks, 1):
            try:
                print(f"[{i}/{len(notebooks)}] {notebook.name}")
                print(f"   UUID: {notebook.uuid}")
                print(f"   Pages: {notebook.page_count or 0}")

                nb_stats = await self._sync_notebook_content(notebook.uuid)
                stats["notebooks"] += 1
                stats["pages"] += nb_stats["uploaded"]
                stats["failed"] += nb_stats["failed"]
                stats["skipped"] += nb_stats.get("skipped", 0)
                stats["rate_limited"] += nb_stats.get("rate_limited", 0)

                if nb_stats.get("rate_limited", 0) > 0:
                    rate_limit_hit = True

                print()

            except QuotaExceededError as e:
                logger.warning(f"Quota exceeded during sync of {notebook.uuid}")
                print(f"   ⚠️  Quota exceeded - stopping content sync")
                break

            except Exception as e:
                logger.error(f"Failed to sync notebook {notebook.uuid}: {e}", exc_info=True)
                print(f"   ❌ Failed: {e}")
                print()
                stats["failed"] += 1

        # ================================================================
        # Summary
        # ================================================================
        print("=" * 70)
        print("  ✅ Initial Sync Complete")
        if phase1_success:
            print(f"     Phase 1: {metadata_result.get('notebooks_created', 0)} notebooks created, "
                  f"{metadata_result.get('pages_registered', 0)} pages registered")
        print(f"     Phase 2: {stats['pages']} pages uploaded")
        if stats["failed"] > 0:
            print(f"     Failed: {stats['failed']}")
        if stats["rate_limited"] > 0:
            print(f"     Rate limited: {stats['rate_limited']} (will retry on next sync)")
        if rate_limit_hit:
            print("\n  💡 Tip: Some pages were rate limited. They'll sync on the next run.")
        print("=" * 70)
        print()

        return {
            **stats,
            "phase1": metadata_result,
        }

    async def _sync_notebook_content(self, notebook_uuid: str) -> dict:
        """
        Sync a single notebook's content (Phase 2).

        Uploads pages (.rm files) in order from newest to oldest (based on .content file),
        respects max_pages_per_notebook config. Page mappings are already established
        by Phase 1 metadata sync, so we don't need to upload .content file.

        Args:
            notebook_uuid: UUID of the notebook

        Returns:
            Statistics dictionary with uploaded, failed, skipped, rate_limited counts
        """
        notebook_dir = self.remarkable_folder / notebook_uuid

        # Check if notebook directory exists
        if not notebook_dir.exists() or not notebook_dir.is_dir():
            logger.warning(f"Notebook directory not found: {notebook_dir}")
            return {"uploaded": 0, "failed": 0, "skipped": 0, "rate_limited": 0}

        stats = {
            "uploaded": 0,
            "failed": 0,
            "skipped": 0,
            "rate_limited": 0,
            "failed_pages": [],  # Track which pages failed
        }

        # 1. Get all page files
        all_page_files = list(notebook_dir.glob("*.rm"))

        if not all_page_files:
            logger.info(f"No pages found in notebook {notebook_uuid}")
            return {"uploaded": 0, "failed": 0, "skipped": 0, "rate_limited": 0}

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

                # Extract page UUIDs - pages can be plain strings or dicts with 'id' field
                # Skip deleted pages (they have 'deleted': {'value': 1} or similar)
                for page_entry in pages_array:
                    if isinstance(page_entry, str):
                        page_order.append(page_entry)
                    elif isinstance(page_entry, dict) and "id" in page_entry:
                        # Check if page is deleted
                        deleted = page_entry.get("deleted", {})
                        if isinstance(deleted, dict) and deleted.get("value"):
                            continue  # Skip deleted pages
                        page_order.append(page_entry["id"])

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

        # 6. Upload pages in order (newest first) with rate limit handling
        if page_files_to_upload:
            print(f"   📤 Uploading {len(page_files_to_upload)} page(s) (newest first)...")

            for page_file in page_files_to_upload:
                try:
                    result = await self._upload_with_retry(page_file, notebook_uuid)
                    if result.get("rate_limited"):
                        stats["rate_limited"] += 1
                        # Don't continue trying if we're rate limited
                        remaining = len(page_files_to_upload) - stats["uploaded"] - stats["rate_limited"]
                        if remaining > 0:
                            print(f"   ⏸️  Rate limited. {remaining} page(s) will sync later.")
                        break
                    stats["uploaded"] += 1
                except QuotaExceededError:
                    # Re-raise to stop the entire sync
                    raise
                except Exception as e:
                    logger.error(f"Failed to upload {page_file.name}: {e}")
                    stats["failed"] += 1
                    stats["failed_pages"].append(page_file.stem)

        # Note: .content file upload is no longer needed here.
        # Phase 1 (metadata sync) establishes page mappings via /sync/metadata endpoint.

        # 7. Report results
        if stats["failed"] > 0:
            print(f"   ⚠️  {stats['failed']} page(s) failed to upload")
            if stats["failed_pages"]:
                logger.warning(f"Failed pages: {stats['failed_pages'][:5]}{'...' if len(stats['failed_pages']) > 5 else ''}")

        if stats["uploaded"] > 0:
            print(f"   ✓ Uploaded {stats['uploaded']} page(s)")

        return stats

    async def _upload_with_retry(
        self, page_file: Path, notebook_uuid: str, max_retries: int = 2
    ) -> dict:
        """
        Upload a page file with exponential backoff on rate limit.

        Args:
            page_file: Path to the .rm file
            notebook_uuid: UUID of the notebook
            max_retries: Maximum number of retries on rate limit (default: 2)

        Returns:
            Dictionary with upload result. Includes "rate_limited": True if
            all retries exhausted due to rate limiting.

        Raises:
            QuotaExceededError: If quota is exceeded
            CloudSyncError: If upload fails for other reasons
        """
        for attempt in range(max_retries + 1):
            try:
                result = await self.cloud_sync.upload_file(page_file, notebook_uuid, "rm")
                return result

            except RateLimitError as e:
                # Rate limited - retry with exponential backoff
                if attempt < max_retries:
                    delay = e.retry_after * (2 ** attempt)
                    logger.info(f"Rate limited. Waiting {delay}s before retry (attempt {attempt + 1}/{max_retries})...")
                    print(f"   ⏳ Rate limited. Waiting {delay}s...")
                    await asyncio.sleep(delay)
                else:
                    # All retries exhausted
                    logger.warning(f"Rate limit exceeded after {max_retries} retries for {page_file.name}")
                    return {"rate_limited": True}

        # Should not reach here, but just in case
        return {"rate_limited": True}


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
