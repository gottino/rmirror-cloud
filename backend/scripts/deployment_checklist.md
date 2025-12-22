# PostgreSQL Migration Deployment Checklist

Use this checklist when performing the production migration.

## Pre-Migration (30 min before)

- [ ] Announce maintenance window to users (if applicable)
- [ ] Verify backup strategy is in place
- [ ] Review POSTGRES_MIGRATION.md guide
- [ ] Prepare rollback plan

## Migration Steps

### Step 1: Backup Current Database ⏱️ 2 min

```bash
ssh deploy@167.235.74.51
cd /var/www/rmirror-cloud/backend
sudo cp rmirror.db rmirror.db.backup.$(date +%Y%m%d_%H%M%S)
ls -lh rmirror.db*
```

- [ ] Backup created successfully
- [ ] Backup size matches original (~5.5M)

### Step 2: Setup PostgreSQL Database ⏱️ 2 min

```bash
export POSTGRES_PASSWORD=$(openssl rand -base64 32)
echo "Password: $POSTGRES_PASSWORD" | tee postgres_password.txt
chmod 600 postgres_password.txt
./scripts/setup_postgres.sh
```

- [ ] Database created
- [ ] User created
- [ ] Password saved securely
- [ ] Connection URL noted

### Step 3: Stop Application (Begin Downtime) ⏱️ 1 min

```bash
sudo systemctl stop rmirror.service
sudo systemctl status rmirror.service
```

- [ ] Service stopped successfully
- [ ] No active connections

### Step 4: Update Configuration ⏱️ 1 min

```bash
# Backup current .env
cp .env .env.sqlite.backup

# Update .env with PostgreSQL URL
nano .env
# Change: DATABASE_URL=postgresql://rmirror:PASSWORD@localhost:5432/rmirror
```

- [ ] .env backed up
- [ ] DATABASE_URL updated
- [ ] Password correct in URL

### Step 5: Run Migrations ⏱️ 1 min

```bash
poetry run alembic upgrade head
```

- [ ] Migrations completed without errors
- [ ] All tables created

### Step 6: Migrate Data ⏱️ 2-5 min

```bash
poetry run python scripts/migrate_sqlite_to_postgres.py \
  --sqlite-path ./rmirror.db \
  --postgres-url "postgresql://rmirror:PASSWORD@localhost:5432/rmirror"
```

- [ ] All tables migrated
- [ ] Row counts verified
- [ ] No errors in output

### Step 7: Start Application (End Downtime) ⏱️ 1 min

```bash
sudo systemctl start rmirror.service
sudo systemctl status rmirror.service
```

- [ ] Service started successfully
- [ ] No errors in status

### Step 8: Verify Application ⏱️ 5 min

```bash
# Check logs
sudo journalctl -u rmirror.service -n 50 --no-pager

# Test API
curl -I https://rmirror.io/health

# Test database connection
psql postgresql://rmirror:PASSWORD@localhost:5432/rmirror -c "SELECT COUNT(*) FROM users;"
```

- [ ] Logs show successful startup
- [ ] API responds with 200 OK
- [ ] Database queries work
- [ ] Dashboard loads
- [ ] Can view notebooks
- [ ] No errors in browser console

## Post-Migration Monitoring (24 hours)

### Immediately After

- [ ] Dashboard loads and shows notebooks
- [ ] Can click into notebook details
- [ ] Agent download works
- [ ] No errors in browser console

### 1 Hour Later

- [ ] Check logs: `sudo journalctl -u rmirror.service --since "1 hour ago" | grep -i error`
- [ ] Verify database connections: `psql postgresql://rmirror:PASSWORD@localhost:5432/rmirror -c "SELECT count(*) FROM pg_stat_activity WHERE datname='rmirror';"`
- [ ] Test API endpoints manually

### 24 Hours Later

- [ ] Review error logs
- [ ] Check database performance
- [ ] Verify no data inconsistencies
- [ ] Monitor disk usage

## Rollback Procedure (if needed)

```bash
# 1. Stop service
sudo systemctl stop rmirror.service

# 2. Restore SQLite config
cp .env.sqlite.backup .env

# 3. Start service
sudo systemctl start rmirror.service

# 4. Verify
curl -I https://rmirror.io/health
```

## Success Criteria

✅ Migration successful if:
- Service starts without errors
- Dashboard loads and displays notebooks
- Can navigate to notebook details
- All row counts match between SQLite and PostgreSQL
- No errors in logs for 1 hour post-migration

## Troubleshooting

### Service won't start

Check logs:
```bash
sudo journalctl -u rmirror.service -n 100 --no-pager
```

Common issues:
- Wrong password in DATABASE_URL
- PostgreSQL not accepting connections
- Missing database permissions

### Data missing

Verify row counts:
```bash
sqlite3 rmirror.db "SELECT COUNT(*) FROM users;"
psql postgresql://rmirror:PASSWORD@localhost:5432/rmirror -c "SELECT COUNT(*) FROM users;"
```

### Connection errors

Check PostgreSQL:
```bash
sudo systemctl status postgresql
sudo tail -20 /var/log/postgresql/postgresql-16-main.log
```

## Notes

**Total downtime estimate:** 5-10 minutes (Steps 3-7)

**Point of no return:** After Step 6 completes successfully, you should continue forward. Only rollback if Step 7 or 8 fails.

**Keep this document open** during the migration for reference.
