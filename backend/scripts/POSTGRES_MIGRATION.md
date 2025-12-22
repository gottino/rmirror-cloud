# PostgreSQL Migration Guide

This guide walks you through migrating your rMirror Cloud production database from SQLite to PostgreSQL.

## Overview

The migration process involves:
1. Setting up PostgreSQL database and user
2. Running Alembic migrations to create the schema
3. Migrating data from SQLite to PostgreSQL
4. Updating configuration and restarting services

**Estimated time:** 15-30 minutes
**Downtime required:** Yes (5-10 minutes)

## Prerequisites

- SSH access to production server
- PostgreSQL 16 installed (already done ✓)
- Backup of current SQLite database
- Root/sudo access on production server

## Step-by-Step Migration

### 1. Backup Current Database

**On production server:**

```bash
# SSH into production
ssh deploy@167.235.74.51

# Navigate to backend directory
cd /var/www/rmirror-cloud/backend

# Create backup
sudo cp rmirror.db rmirror.db.backup.$(date +%Y%m%d_%H%M%S)
ls -lh rmirror.db*
```

### 2. Setup PostgreSQL Database

**On production server:**

```bash
# Generate a secure password
export POSTGRES_PASSWORD=$(openssl rand -base64 32)
echo "Save this password: $POSTGRES_PASSWORD"

# Run setup script
./scripts/setup_postgres.sh
```

This will output your database connection URL. **Save it!**

### 3. Run Database Migrations

**On production server:**

```bash
# Update .env with PostgreSQL URL
nano .env

# Add/update this line (use the URL from step 2):
# DATABASE_URL=postgresql://rmirror:YOUR_PASSWORD@localhost:5432/rmirror

# Run Alembic migrations to create schema
poetry run alembic upgrade head
```

### 4. Migrate Data from SQLite to PostgreSQL

**On production server:**

```bash
# Run migration script
poetry run python scripts/migrate_sqlite_to_postgres.py \
  --sqlite-path ./rmirror.db \
  --postgres-url "postgresql://rmirror:YOUR_PASSWORD@localhost:5432/rmirror"
```

The script will:
- Migrate all tables in dependency order
- Reset PostgreSQL sequences
- Verify row counts match

### 5. Test the Migration

**On production server:**

```bash
# Connect to PostgreSQL and check data
psql postgresql://rmirror:YOUR_PASSWORD@localhost:5432/rmirror

# Inside psql:
\dt                          # List tables
SELECT COUNT(*) FROM users;  # Check user count
SELECT COUNT(*) FROM notebooks;  # Check notebook count
\q                           # Exit psql

# Compare with SQLite
sqlite3 rmirror.db "SELECT COUNT(*) FROM users;"
sqlite3 rmirror.db "SELECT COUNT(*) FROM notebooks;"
```

### 6. Restart Services

**On production server:**

```bash
# Restart the backend service
sudo systemctl restart rmirror.service

# Check status
sudo systemctl status rmirror.service

# Check logs
sudo journalctl -u rmirror.service -f
```

### 7. Verify Application

**From your local machine:**

```bash
# Test API health endpoint
curl https://rmirror.io/health

# Check that dashboard loads and shows your notebooks
# Visit: https://rmirror.io
```

## Rollback Plan

If something goes wrong:

```bash
# On production server:

# 1. Stop the service
sudo systemctl stop rmirror.service

# 2. Restore SQLite configuration in .env
nano .env
# Change back to: DATABASE_URL=sqlite:///./rmirror.db

# 3. Restart service
sudo systemctl start rmirror.service
```

## Security Notes

1. **Password Security**: Store the PostgreSQL password securely (password manager)
2. **Backup Retention**: Keep the SQLite backup for at least 7 days
3. **Access Control**: PostgreSQL is configured to only accept local connections

## Performance Tuning (Optional)

After migration, you may want to tune PostgreSQL for better performance:

```bash
# Edit PostgreSQL config
sudo nano /etc/postgresql/16/main/postgresql.conf

# Recommended settings for a server with 2-4GB RAM:
shared_buffers = 256MB
effective_cache_size = 1GB
maintenance_work_mem = 64MB
work_mem = 16MB
max_connections = 100

# Restart PostgreSQL
sudo systemctl restart postgresql
```

## Monitoring

Check database size:

```bash
psql postgresql://rmirror:YOUR_PASSWORD@localhost:5432/rmirror -c "SELECT pg_size_pretty(pg_database_size('rmirror'));"
```

Monitor connections:

```bash
psql postgresql://rmirror:YOUR_PASSWORD@localhost:5432/rmirror -c "SELECT count(*) FROM pg_stat_activity WHERE datname='rmirror';"
```

## Troubleshooting

### Migration script fails with "table does not exist"

Some tables may not exist in your current schema. The script skips these automatically.

### Row counts don't match

Check the script output for which tables differ. May need manual verification.

### Connection refused

Ensure PostgreSQL is running:

```bash
sudo systemctl status postgresql
```

### Permission denied

Ensure the rmirror user has proper permissions:

```bash
sudo -u postgres psql -d rmirror -c "GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO rmirror;"
```

## Cleanup (After 7 Days)

Once you're confident everything works:

```bash
# Remove SQLite backup
rm rmirror.db.backup.*

# (Optional) Remove SQLite database
rm rmirror.db
```

## Need Help?

If you encounter any issues during migration, check:
1. Service logs: `sudo journalctl -u rmirror.service -n 100`
2. PostgreSQL logs: `sudo tail -f /var/log/postgresql/postgresql-16-main.log`
3. Application logs: Check backend logs for database connection errors
