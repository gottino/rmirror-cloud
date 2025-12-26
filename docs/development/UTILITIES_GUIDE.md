# rMirror Cloud Utilities Guide

This guide documents all utility scripts available in the rMirror Cloud backend for managing your database, monitoring sync status, and maintaining data integrity.

## Table of Contents

- [OCR Hash Management](#ocr-hash-management)
- [Sync Integrity Tools](#sync-integrity-tools)
- [PostgreSQL Migration](#postgresql-migration)
- [Database Maintenance](#database-maintenance)
- [Best Practices](#best-practices)

## OCR Hash Management

### Overview

The hash management utilities help maintain the OCR deduplication system by ensuring all pages have SHA-256 file hashes. This prevents unnecessary re-processing of unchanged files.

### backfill_page_hashes.py

**Purpose:** Backfill SHA-256 file hashes for existing pages without hashes.

**Usage:**
```bash
poetry run python backfill_page_hashes.py /path/to/remarkable/source
```

**Example:**
```bash
poetry run python backfill_page_hashes.py \
  "/Users/gabriele/Library/Containers/com.remarkable.desktop/Data/Library/Application Support/remarkable/desktop"
```

**What it does:**
- Finds pages in database without `file_hash` values
- Only processes pages updated before December 1, 2025
- Filters for handwritten notebooks (excludes PDFs and EPUBs)
- Reads corresponding `.rm` files from reMarkable source directory
- Calculates SHA-256 hash for each file
- Updates database with hash values

**Output Example:**
```
Using reMarkable source directory: /Users/gabriele/Library/.../remarkable/desktop
Found 1,234 pages without file hashes (updated before 2025-12-01)

Processing 1,234 pages...
[1/1234] Notebook: Project Notes, Page: abc123def456...
   File: /Users/gabriele/Library/.../abc123def456.rm
   Hash: 8f3d2a1b9c4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a
   ✓ Updated page ID 456

[2/1234] Notebook: Meeting Notes, Page: def789ghi012...
   File: /Users/gabriele/Library/.../def789ghi012.rm
   Hash: 1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2
   ✓ Updated page ID 457

...

Progress: 1234/1234 pages processed
Success: 1234, Failed: 0, Skipped: 0

Time elapsed: 2m 34s
```

**When to use:**
- After deploying the OCR deduplication system for the first time
- When migrating from an older version without hash support
- After database restoration from backup
- If hash coverage report shows low coverage

**Common Issues:**

**Issue:** Can't find `.rm` files
```
ERROR: Source directory does not exist: /path/to/remarkable/source
```
**Solution:** Verify the reMarkable Desktop app path. On macOS, it's typically:
```
/Users/YOUR_USERNAME/Library/Containers/com.remarkable.desktop/Data/Library/Application Support/remarkable/desktop
```

**Issue:** Permission denied
```
ERROR: Permission denied reading file: abc123.rm
```
**Solution:** Ensure the Python process has read permissions:
```bash
chmod -R u+r "/Users/YOUR_USERNAME/Library/Containers/com.remarkable.desktop"
```

---

### backfill_by_metadata.py

**Purpose:** Advanced hash backfilling using notebook metadata files for more comprehensive coverage.

**Usage:**
```bash
poetry run python backfill_by_metadata.py /path/to/remarkable/source
```

**What it does:**
- Scans all `.metadata` files in the reMarkable source directory
- Identifies all notebooks by UUID
- Matches notebooks in database with local files
- Processes all pages for each matched notebook
- More comprehensive than basic backfilling

**When to use:**
- When basic backfilling misses pages
- For complete coverage of all notebooks
- When you want metadata-driven discovery of notebooks

**Output Example:**
```
Scanning metadata files...
Found 25 notebook metadata files

Processing notebooks:
[1/25] Project Notes (abc123...)
   Found in database: ✓
   Processing 125 pages...
   Backfilled: 15 pages
   Skipped (already have hash): 110 pages

[2/25] Meeting Notes (def456...)
   Found in database: ✓
   Processing 45 pages...
   Backfilled: 5 pages
   Skipped (already have hash): 40 pages

...

Summary:
Total notebooks: 25
Total pages processed: 3,450
Hashes backfilled: 250
Already had hashes: 3,200
Failed: 0
```

---

### backfill_specific_notebooks.py

**Purpose:** Backfill hashes for specific notebooks by UUID.

**Usage:**
```bash
# Edit the script to specify notebook UUIDs
poetry run python backfill_specific_notebooks.py
```

**Configuration:**
Edit the script to specify target notebooks:
```python
NOTEBOOK_UUIDS = [
    "abc123-def456-ghi789",
    "jkl012-mno345-pqr678",
]
```

**What it does:**
- Processes only specified notebooks
- Useful for targeted backfilling
- Faster than full backfilling when you know which notebooks need attention

**When to use:**
- When only specific notebooks need hash backfilling
- For testing hash backfilling on a subset of notebooks
- When full backfilling is too slow or unnecessary

---

## Sync Integrity Tools

### hash_coverage_report.py

**Purpose:** Generate comprehensive hash coverage report across all notebooks.

**Usage:**
```bash
poetry run python hash_coverage_report.py
```

**What it shows:**
- Hash coverage per notebook (percentage with/without hashes)
- OCR text availability
- Pages in `.content` files but missing from database
- Overall statistics across all notebooks

**Output Example:**
```
╔══════════════════════════════════════════════════════════════════════╗
║                      Hash Coverage Report                            ║
╚══════════════════════════════════════════════════════════════════════╝

┌─────────────────────────────────────────────────────────────────────┐
│ Project Notes                                                       │
├─────────────────────────────────────────────────────────────────────┤
│ Pages in DB:        125                                             │
│ Pages with hash:    125 (100%)                                      │
│ Pages without hash: 0   (0%)                                        │
│ Pages with text:    120 (96%)                                       │
│ Missing in DB:      0                                               │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│ Meeting Notes                                                       │
├─────────────────────────────────────────────────────────────────────┤
│ Pages in DB:        45                                              │
│ Pages with hash:    40  (89%)                                       │
│ Pages without hash: 5   (11%)                                       │
│ Pages with text:    45  (100%)                                      │
│ Missing in DB:      2                                               │
└─────────────────────────────────────────────────────────────────────┘

╔══════════════════════════════════════════════════════════════════════╗
║                         Summary Statistics                           ║
╚══════════════════════════════════════════════════════════════════════╝

Total notebooks:          25
Total pages in DB:        3,450
Pages with hash:          3,200 (93%)
Pages without hash:       250   (7%)
Pages with OCR text:      3,400 (99%)
Pages missing from DB:    15

Hash coverage: ████████████████████████████░░░░ 93%
```

**Interpreting the report:**

- **Pages with hash: 100%** = Perfect! All pages have hashes, OCR deduplication working optimally
- **Pages with hash: <95%** = Run hash backfilling to improve coverage
- **Missing in DB: >0** = Some pages in `.content` files aren't synced yet - use Initial Sync
- **Pages with text: <90%** = Some OCR processing may have failed - check logs

**When to use:**
- Regularly (weekly) to monitor hash coverage
- After running backfilling scripts to verify success
- Before/after database migrations
- When troubleshooting OCR performance issues

---

### show_missing_pages_summary.py

**Purpose:** Quick summary of pages that exist in `.content` files but are missing from the database.

**Usage:**
```bash
poetry run python show_missing_pages_summary.py
```

**Output Example:**
```
Scanning notebooks for missing pages...

Notebooks with missing pages:

Project Notes (uuid: abc123-def456-ghi789)
  Missing pages: 2
  UUIDs: ['page1-uuid-abc', 'page2-uuid-def']

Meeting Notes (uuid: def456-ghi789-jkl012)
  Missing pages: 1
  UUIDs: ['page3-uuid-ghi']

Summary:
Total notebooks checked: 25
Notebooks with missing pages: 2
Total pages missing from database: 3
```

**What to do with missing pages:**
1. Open agent web UI at http://localhost:5555
2. Click "Initial Sync" button
3. Wait for sync to complete
4. Re-run this script to verify pages were uploaded

**When to use:**
- After adding notebooks to reMarkable tablet offline
- After changing notebook selection in agent
- When pages don't appear in web dashboard
- To diagnose sync issues

---

### check_content_vs_db.py

**Purpose:** Verify sync integrity by comparing database state with `.content` files.

**Usage:**
```bash
poetry run python check_content_vs_db.py
```

**Output Example:**
```
Checking sync integrity...

✓ Project Notes: All 125 pages synced
✗ Meeting Notes: 2 pages missing from database
  Missing UUIDs: ['abc-123', 'def-456']
✓ Research Ideas: All 34 pages synced
✓ Todo Lists: All 67 pages synced
✗ Daily Journal: 1 page missing from database
  Missing UUIDs: ['ghi-789']

╔══════════════════════════════════════════════════════════════════════╗
║                         Sync Integrity Report                        ║
╚══════════════════════════════════════════════════════════════════════╝

Total notebooks: 25
Fully synced: 23 (92%)
With missing pages: 2 (8%)
Total pages missing: 3
Total pages checked: 3,450
```

**When to use:**
- Before important operations (migrations, backups)
- To diagnose "why don't I see my pages?" issues
- After running Initial Sync to verify success
- As part of regular health checks

---

## PostgreSQL Migration

### migrate_to_postgres.sh

**Purpose:** Fully automated migration from SQLite to PostgreSQL.

**Usage:**
```bash
# SSH to production
ssh deploy@your-server.com
cd /var/www/rmirror-cloud/backend

# Run automated migration
sudo -E ./scripts/migrate_to_postgres.sh
```

**What it does:**
1. Creates PostgreSQL database and user
2. Backs up SQLite database
3. Updates .env configuration
4. Runs Alembic migrations to create schema
5. Migrates all data from SQLite to PostgreSQL
6. Restarts backend service
7. Verifies migration success

**Output Example:**
```
╔══════════════════════════════════════════════════════════════════════╗
║           rMirror PostgreSQL Migration Script                        ║
╚══════════════════════════════════════════════════════════════════════╝

[1/7] Checking prerequisites...
   ✓ PostgreSQL 16 is installed
   ✓ SQLite database found: rmirror.db (12.5 MB)
   ✓ Python environment ready

[2/7] Creating PostgreSQL database...
   ✓ Database 'rmirror' created
   ✓ User 'rmirror' created with secure password
   ✓ Permissions granted

[3/7] Backing up SQLite database...
   ✓ Backup created: rmirror.db.backup.20251226_143022

[4/7] Updating .env configuration...
   ✓ DATABASE_URL updated to PostgreSQL
   ✓ Previous .env backed up to .env.backup

[5/7] Running database migrations...
   ✓ Alembic migrations applied
   ✓ Schema created in PostgreSQL

[6/7] Migrating data...
   ✓ Migrated users: 145 rows
   ✓ Migrated notebooks: 1,234 rows
   ✓ Migrated pages: 45,678 rows
   ✓ Migrated todos: 3,456 rows
   ✓ All sequences reset

[7/7] Restarting service...
   ✓ rmirror.service restarted
   ✓ Service is running

╔══════════════════════════════════════════════════════════════════════╗
║                    Migration Complete!                               ║
╚══════════════════════════════════════════════════════════════════════╝

Your rMirror backend is now using PostgreSQL.

Next steps:
1. Test the application at https://your-domain.com
2. Keep the SQLite backup for 7 days: rmirror.db.backup.20251226_143022
3. Monitor the service: sudo systemctl status rmirror.service

Database URL: postgresql://rmirror:***@localhost:5432/rmirror
```

**Documentation:** See [PostgreSQL Migration Guide](scripts/POSTGRES_MIGRATION.md) for complete details.

---

## Database Maintenance

### Test User Cleanup

**Purpose:** Remove test users and their data from the database.

**Location:** `scripts/cleanup_test_users.py`

**Usage:**
```bash
poetry run python scripts/cleanup_test_users.py
```

**What it does:**
- Identifies test users (by email pattern)
- Removes user and all associated data
- Useful for development/staging environments

---

## Best Practices

### Regular Maintenance Schedule

**Weekly:**
- Run hash coverage report
- Check for missing pages
- Review sync integrity

**Monthly:**
- Review database size and growth
- Check for orphaned files in S3
- Verify backups are working

**After Major Changes:**
- Code deployments → Verify service is running
- Database migrations → Run integrity checks
- Configuration changes → Test with coverage report

### Monitoring Commands

```bash
# Quick health check
poetry run python hash_coverage_report.py | grep "Hash coverage"

# Check for missing pages
poetry run python show_missing_pages_summary.py | grep "Total pages missing"

# Verify sync integrity
poetry run python check_content_vs_db.py | grep "Total notebooks"
```

### Automation Ideas

**Cron job for daily coverage check:**
```bash
# Add to crontab
0 2 * * * cd /var/www/rmirror-cloud/backend && poetry run python hash_coverage_report.py > /var/log/rmirror/hash_coverage.log 2>&1
```

**Alert on low coverage:**
```bash
#!/bin/bash
COVERAGE=$(poetry run python hash_coverage_report.py | grep "Hash coverage" | awk '{print $3}' | tr -d '%')
if [ "$COVERAGE" -lt 90 ]; then
    echo "WARNING: Hash coverage below 90%: ${COVERAGE}%" | mail -s "rMirror Hash Coverage Alert" admin@example.com
fi
```

### Safety Guidelines

1. **Always backup before running utilities:**
   ```bash
   cp rmirror.db rmirror.db.backup.$(date +%Y%m%d_%H%M%S)
   ```

2. **Test on development first:**
   - Run utilities on development database
   - Verify results before running on production

3. **Monitor during execution:**
   - Watch script output for errors
   - Check database size during operations
   - Monitor system resources (CPU, memory, disk)

4. **Verify after completion:**
   - Run coverage report after backfilling
   - Check sync integrity after migrations
   - Test application functionality

### Troubleshooting

**Script hangs or runs very slowly:**
- Check database locks: `SELECT * FROM pg_locks WHERE granted = false;` (PostgreSQL)
- Stop other database-intensive processes
- Run during low-traffic periods

**Permission errors:**
```bash
# Fix file permissions
chmod +x backfill_page_hashes.py
chmod +x scripts/migrate_to_postgres.sh

# Ensure database access
poetry run python -c "from app.database import engine; print(engine.url)"
```

**Memory issues with large databases:**
- Process notebooks in batches
- Use `backfill_specific_notebooks.py` instead of full backfilling
- Increase available memory or run on larger instance

## Related Documentation

- [OCR Deduplication Guide](OCR_DEDUPLICATION.md) - Complete deduplication system documentation
- [PostgreSQL Migration Guide](scripts/POSTGRES_MIGRATION.md) - Detailed migration instructions
- [Initial Sync Feature](../agent/INITIAL_SYNC_FEATURE.md) - Bulk upload documentation
- [Backend README](README.md) - General backend documentation

## Support

For issues with utilities:

1. Check script output for specific error messages
2. Review the Troubleshooting section above
3. Verify database connection and permissions
4. Check the relevant detailed guide for your operation
5. Open a GitHub issue with:
   - Script name and command used
   - Complete error output
   - Database type (SQLite/PostgreSQL)
   - Coverage report output (if applicable)
