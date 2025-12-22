# PostgreSQL Migration Scripts

## Quick Start

Run the fully automated migration on your production server:

```bash
ssh deploy@167.235.74.51
cd /var/www/rmirror-cloud/backend
git pull
sudo -E ./scripts/migrate_to_postgres.sh
```

**That's it!** The script handles everything automatically with no manual editing required.

## What It Does

The automated script:
1. ✓ Creates PostgreSQL database and user with secure password
2. ✓ Backs up your SQLite database
3. ✓ Updates .env with PostgreSQL connection URL
4. ✓ Runs Alembic migrations
5. ✓ Migrates all data from SQLite to PostgreSQL
6. ✓ Verifies data integrity
7. ✓ Restarts the service

**Downtime:** 5-10 minutes
**Automatic rollback:** If migration fails, reverts to SQLite

## Files

- **migrate_to_postgres.sh** - Fully automated migration (recommended)
- **migrate_sqlite_to_postgres.py** - Data migration script (used by above)
- **setup_postgres.sh** - PostgreSQL setup only (for manual migration)
- **POSTGRES_MIGRATION.md** - Detailed documentation
- **deployment_checklist.md** - Manual migration checklist

## After Migration

The script saves:
- `.postgres_password` - Your PostgreSQL password
- `rmirror.db.backup.TIMESTAMP` - SQLite backup
- `.env.backup.TIMESTAMP` - Original .env

Keep these backups for 7 days.

## Rollback

If you need to revert to SQLite:

```bash
sudo systemctl stop rmirror.service
sudo cp .env.backup.* .env
sudo systemctl start rmirror.service
```
