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
from collections.abc import Callable
from pathlib import Path
from typing import Optional

from app.config import Config
from app.remarkable.metadata_scanner import MetadataScanner
from app.sync.cloud_sync import (
    AuthenticationRequiredError,
    CloudSync,
    CloudSyncError,
    QuotaExceededError,
    RateLimitError,
)
from app.sync.manifest import Fingerprint, UploadManifest, fingerprint_file
from app.sync.metadata_sync import MetadataSync

logger = logging.getLogger(__name__)


class InitialSync:
    """
    Handles initial synchronization of all notebooks to the cloud.

    Uses a two-phase approach:
    1. Metadata sync (fast): Creates notebook structure immediately
    2. Content sync (slow): Uploads pages with rate limit handling
    """

    # Server errors (5xx) and network errors: retries per page, with backoff
    SERVER_ERROR_RETRIES = 2
    SERVER_ERROR_BACKOFF_SECONDS = 2

    def __init__(
        self,
        config: Config,
        cloud_sync: CloudSync,
        manifest: UploadManifest | None = None,
        on_progress: Callable[[dict], None] | None = None,
    ):
        """
        Initialize initial sync.

        Args:
            config: Agent configuration
            cloud_sync: Cloud sync client
            manifest: Upload manifest; pages uploaded here are recorded in it so the
                watcher does not upload them again (defaults to the config directory's)
            on_progress: Called with a copy of ``progress`` whenever a count changes
        """
        self.config = config
        self.cloud_sync = cloud_sync
        self.manifest = manifest if manifest is not None else UploadManifest.for_config(config)
        self.remarkable_folder = Path(config.remarkable.source_directory)
        self.metadata_sync = MetadataSync(config, cloud_sync)
        self._on_progress = on_progress
        self._sleep = asyncio.sleep  # injectable for tests
        self.progress = {
            "notebooks_total": 0,
            "notebooks_done": 0,
            "uploaded": 0,
            "failed": 0,
            "skipped": 0,
            "rate_limited": 0,
        }
        # Set when the content sync ran into a condition that affects every page
        # left: "quota" (stopped) or "sign_in" (the sign-in was rejected). Reported
        # as "stopped_reason" in the returned stats; it does not change the flow.
        self.stopped_reason: str | None = None

    def _count(self, key: str, amount: int = 1) -> None:
        """Add to a live progress count and report it."""
        self.progress[key] += amount
        self._report_progress()

    def _report_progress(self) -> None:
        if self._on_progress is None:
            return
        try:
            self._on_progress(dict(self.progress))
        except Exception as e:  # Progress reporting must never break the sync
            logger.debug(f"Progress callback failed: {e}")

    async def run(self, selected_notebook_uuids: Optional[list[str]] = None) -> dict:
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
            metadata_uuids = selected_notebook_uuids
            if metadata_uuids is not None:
                excluded_uuids = set(self.config.sync.excluded_notebooks)
                metadata_uuids = [u for u in metadata_uuids if u not in excluded_uuids]
            metadata_result = await self.metadata_sync.run(metadata_uuids)
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

        # Filter by selection; notebooks deleted on the server are never re-uploaded here
        if selected_notebook_uuids is not None:
            notebooks = [nb for nb in notebooks if nb.uuid in selected_notebook_uuids]
        excluded = set(self.config.sync.excluded_notebooks)
        notebooks = [nb for nb in notebooks if nb.uuid not in excluded]

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
        self.progress["notebooks_total"] = len(notebooks)
        self._report_progress()
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

                self._count("notebooks_done")
                print()

                if nb_stats.get("stopped") == "sign_in":
                    self.stopped_reason = "sign_in"
                    logger.warning("Sign-in required during initial sync; stopping")
                    print("   ⚠️  Sign-in required - stopping content sync")
                    # The notebooks not reached: leave their pages for the rescan too
                    for later in notebooks[i:]:
                        pages, skipped = self._plan_pages(later.uuid)
                        stats["rate_limited"] += self._defer(pages)
                        if skipped:
                            stats["skipped"] += skipped
                            self._count("skipped", skipped)
                    break

            except QuotaExceededError:
                self.stopped_reason = "quota"
                logger.warning(f"Quota exceeded during sync of {notebook.uuid}")
                print("   ⚠️  Quota exceeded - stopping content sync")
                break

            except Exception as e:
                logger.error(f"Failed to sync notebook {notebook.uuid}: {e}", exc_info=True)
                print(f"   ❌ Failed: {e}")
                print()
                stats["failed"] += 1
                self._count("failed")
                self._count("notebooks_done")

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
            "stopped_reason": self.stopped_reason,
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
        stats = {
            "uploaded": 0,
            "failed": 0,
            "skipped": 0,
            "rate_limited": 0,
            "failed_pages": [],  # Track which pages failed
        }

        page_files_to_upload, skipped_count = self._plan_pages(notebook_uuid)
        if skipped_count:
            max_pages = self.config.sync.max_pages_per_notebook
            stats["skipped"] = skipped_count
            self._count("skipped", skipped_count)
            print(f"   ⚡ Limiting to {max_pages} most recent pages (skipping {skipped_count} older pages)")
            logger.info(f"Limited notebook {notebook_uuid} to {max_pages} newest pages")

        # 6. Upload pages in order (newest first) with rate limit handling
        if page_files_to_upload:
            print(f"   📤 Uploading {len(page_files_to_upload)} page(s) (newest first)...")

            for index, page_file in enumerate(page_files_to_upload):
                try:
                    fingerprint = fingerprint_file(page_file)
                    result = await self._upload_with_retry(page_file, notebook_uuid)
                    if result.get("rate_limited"):
                        # This page and the rest of the notebook: left for the
                        # next rescan, counted as will-retry
                        deferred = self._defer(page_files_to_upload[index:])
                        stats["rate_limited"] += deferred
                        print(f"   ⏸️  Rate limited. {deferred} page(s) will sync later.")
                        break
                    self._record_upload(page_file, fingerprint)
                    stats["uploaded"] += 1
                    self._count("uploaded")
                except QuotaExceededError:
                    # Re-raise to stop the entire sync
                    raise
                except AuthenticationRequiredError:
                    # Signed out: every page left would fail the same way. Leave them
                    # for the rescan that runs after the next sign-in, and stop.
                    stats["rate_limited"] += self._defer(page_files_to_upload[index:])
                    stats["stopped"] = "sign_in"
                    break
                except Exception as e:
                    logger.error(f"Failed to upload {page_file.name}: {e}")
                    stats["failed"] += 1
                    stats["failed_pages"].append(page_file.stem)
                    self._count("failed")
                    if isinstance(e, CloudSyncError) and e.transient:
                        self._leave_for_rescan(page_file)

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

    def _plan_pages(self, notebook_uuid: str) -> tuple[list[Path], int]:
        """The notebook's page files to upload, newest first and within the page
        limit, and how many older pages the limit leaves out."""
        notebook_dir = self.remarkable_folder / notebook_uuid

        # Check if notebook directory exists
        if not notebook_dir.exists() or not notebook_dir.is_dir():
            logger.warning(f"Notebook directory not found: {notebook_dir}")
            return [], 0

        # 1. Get all page files
        all_page_files = list(notebook_dir.glob("*.rm"))

        if not all_page_files:
            logger.info(f"No pages found in notebook {notebook_uuid}")
            return [], 0

        # 2. Read .content file to get authoritative page order
        # In reMarkable's .content file, pages array is ordered oldest to newest
        content_file = self.remarkable_folder / f"{notebook_uuid}.content"
        page_order = []  # List of page UUIDs in order (oldest to newest)

        if content_file.exists():
            try:
                with open(content_file) as f:
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
            logger.warning("No page order from .content, falling back to file mtime")
            ordered_page_files = sorted(
                all_page_files,
                key=lambda p: p.stat().st_mtime,
                reverse=True  # Newest first
            )

        max_pages = self.config.sync.max_pages_per_notebook
        if max_pages is not None and max_pages > 0 and len(ordered_page_files) > max_pages:
            return ordered_page_files[:max_pages], len(ordered_page_files) - max_pages
        return ordered_page_files, 0

    def _defer(self, page_files: list[Path]) -> int:
        """Leave pages for the next rescan (not uploaded, not baselined); count them as will-retry."""
        for page_file in page_files:
            self._leave_for_rescan(page_file)
        if page_files:
            self._count("rate_limited", len(page_files))
        return len(page_files)

    def _record_upload(self, page_file: Path, fingerprint: Fingerprint) -> None:
        """Record an uploaded page in the manifest; a failure here must not fail the sync."""
        try:
            self.manifest.record_upload(page_file, fingerprint)
        except Exception as e:
            logger.warning(f"Could not record {page_file.name} in upload manifest: {e}")

    def _leave_for_rescan(self, page_file: Path) -> None:
        """Drop a page's baseline entry so the next start-up scan uploads it.

        The page is never recorded as uploaded on failure; but a page that was only
        baselined (present when the manifest was first set up) would otherwise look
        unchanged to the scan and never be retried.
        """
        try:
            self.manifest.forget_baseline(page_file)
        except Exception as e:
            logger.warning(f"Could not mark {page_file.name} for retry: {e}")

    async def _upload_with_retry(
        self, page_file: Path, notebook_uuid: str, max_retries: int = 2
    ) -> dict:
        """
        Upload a page file with exponential backoff on rate limits, server errors
        (5xx) and network errors (``SERVER_ERROR_RETRIES`` retries for those).

        Args:
            page_file: Path to the .rm file
            notebook_uuid: UUID of the notebook
            max_retries: Maximum number of retries on rate limit (default: 2)

        Returns:
            Dictionary with upload result. Includes "rate_limited": True if
            all retries exhausted due to rate limiting.

        Raises:
            QuotaExceededError: If quota is exceeded
            CloudSyncError: If upload fails for other reasons, or a server or
                network error persists after the retries
        """
        attempt = 0
        server_errors = 0
        while True:
            try:
                result = await self.cloud_sync.upload_file(page_file, notebook_uuid, "rm")
                return result

            except RateLimitError as e:
                # Rate limited - retry with exponential backoff
                if attempt < max_retries:
                    delay = e.retry_after * (2 ** attempt)
                    attempt += 1
                    logger.info(f"Rate limited. Waiting {delay}s before retry (attempt {attempt}/{max_retries})...")
                    print(f"   ⏳ Rate limited. Waiting {delay}s...")
                    await self._sleep(delay)
                else:
                    # All retries exhausted
                    logger.warning(f"Rate limit exceeded after {max_retries} retries for {page_file.name}")
                    return {"rate_limited": True}

            except CloudSyncError as e:
                if not e.transient or server_errors >= self.SERVER_ERROR_RETRIES:
                    raise
                delay = self.SERVER_ERROR_BACKOFF_SECONDS * (2 ** server_errors)
                server_errors += 1
                logger.warning(
                    f"Upload of {page_file.name} failed ({e}); retrying in {delay}s "
                    f"(attempt {server_errors}/{self.SERVER_ERROR_RETRIES})"
                )
                print(f"   ⚠️  Upload failed, retrying in {delay}s...")
                await self._sleep(delay)


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
