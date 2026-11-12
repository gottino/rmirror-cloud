# Backups, restore drill and basic monitoring

This page covers what protects the data when the single server fails:
nightly off-site database dumps, an escrowed copy of the server `.env`, a
tested restore procedure, swap, and external monitoring. The repository ships
the scripts and unit files; the steps below are done by hand on the server.

What exists in the repository:

| File | Purpose |
|------|---------|
| `backend/scripts/backup-db.sh` | `pg_dump -Fc`, size check, keep newest 7 local files, optional upload |
| `backend/config/systemd/rmirror-backup.service` / `.timer` | Run the script daily |
| `backend/config/systemd/memory-limits.conf.example` | `MemoryHigh`/`MemoryMax` drop-in for the backend units |

The pre-deploy dump in `deploy-production.yml` and `deploy.sh` is separate: it
now aborts the deploy if `pg_dump` fails or the file is under 1 KiB, and prunes
pre-deploy dumps older than 14 days. It is a safety net for a deploy, not a
backup strategy, because it lives on the same disk.

## 1. Create a separate backup bucket and a write-only key

Use a bucket that is NOT the one holding user files, with its own application
key, so that a leak of the app credentials cannot delete the backups.

1. In your S3-compatible provider, create a new private bucket used only for
   database dumps.
2. Create an application key restricted to that bucket with write (upload)
   permission only. Do not grant read, list or delete if the provider allows
   it; if a provider cannot separate them, accept the weaker key and keep the
   bucket versioned.
3. Add a lifecycle rule. Suggestion: keep each file version 30 days and then
   delete it (adjust to taste; 30 days of nightly dumps is small).
4. Note the endpoint URL, bucket name and key pair for the next step. Do not
   commit them anywhere.

## 2. Install the AWS CLI

The script supports `aws s3 cp --endpoint-url` only. Install the AWS CLI v2
on the server (see the AWS documentation), then check `aws --version` as the
deploy user. If upload is configured and the CLI is missing, the backup fails
loudly instead of silently keeping local copies.

## 3. Install the timer

```bash
# Environment file (not in the repository). Mode 600, readable by deploy only.
sudo mkdir -p /etc/rmirror
sudo install -m 600 -o deploy -g deploy /dev/null /etc/rmirror/backup.env
sudo -e /etc/rmirror/backup.env
```

Contents (placeholders):

```
BACKUP_DB_NAME=rmirror
BACKUP_PG_SUDO_USER=postgres
BACKUP_S3_BUCKET=<backup bucket>
BACKUP_S3_ENDPOINT=<S3 endpoint URL>
BACKUP_S3_ACCESS_KEY=<write-only key id>
BACKUP_S3_SECRET_KEY=<write-only key secret>
# Optional: BACKUP_S3_REGION, BACKUP_DIR (default /var/backups/rmirror/nightly), BACKUP_KEEP (default 7)
```

`BACKUP_PG_SUDO_USER=postgres` relies on the sudo rule created by
`backend/scripts/setup-deploy-permissions.sh` (deploy may run `pg_dump` as
`postgres`). For staging, use a second env file and a copy of the service with
a different `BACKUP_DB_NAME` if you want it backed up.

```bash
cd /var/www/rmirror-cloud/backend/config/systemd
sudo cp rmirror-backup.service rmirror-backup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now rmirror-backup.timer

# Test once right now and check the result
sudo systemctl start rmirror-backup.service
journalctl -u rmirror-backup.service -n 30 --no-pager
systemctl list-timers rmirror-backup.timer
```

A failed run leaves the unit in `failed` state (`systemctl --failed`). The
script never prints the keys. Check the bucket for the new file after the
first run.

## 4. Escrow the server `.env`

The server `.env` holds `INTEGRATION_MASTER_KEY`. Without it, stored
integration credentials (Notion, Todoist, Obsidian and so on) cannot be
decrypted, even with a perfect database restore. It is not in the database dump.

1. Copy the `.env` (at least `INTEGRATION_MASTER_KEY` and `SECRET_KEY`) into a
   password manager entry as a secure note or attachment.
2. Do it again whenever the `.env` changes, and note the date in the entry.
3. Do not store it in the backup bucket or in the repository.

## 5. Restore drill

Run this on a scratch database, never against the live one. It needs a dump
file: download one from the bucket (with a key that can read) or use the newest
file in the local backup directory.

1. `ls -1t /var/backups/rmirror/nightly/ | head -3` (pick the newest dump).
2. `sudo -u postgres createdb rmirror_restore_test`
3. `sudo -u postgres pg_restore --no-owner -d rmirror_restore_test /var/backups/rmirror/nightly/<file>.dump`
4. Row-count sanity checks, compared with the live database:
   `sudo -u postgres psql rmirror_restore_test -c "SELECT (SELECT count(*) FROM users) AS users, (SELECT count(*) FROM notebooks) AS notebooks, (SELECT count(*) FROM pages) AS pages, (SELECT count(*) FROM sync_records) AS sync_records;"`
   and the same query against `rmirror`. Counts should match or be slightly
   lower (rows written since the dump).
5. `sudo -u postgres psql rmirror_restore_test -c "SELECT max(created_at) FROM pages;"` and check it is recent.
6. `sudo -u postgres dropdb rmirror_restore_test`
7. Record the date and result in the table below, in the same commit or PR.

If the real disaster happens: restore into a new database the same way, point
`DATABASE_URL` at it, and put the escrowed `.env` values back.

### Drill log

| Date | Dump used | Result | Done by |
|------|-----------|--------|---------|
| _not yet run_ | | | |

Repeat the drill at least every quarter, and after any change to the backup
script.

## 6. Swap and memory limits

The server has 4 GB of RAM shared by PostgreSQL, two backend instances, the
dashboard and nginx. A small swap file avoids hard OOM kills during spikes:

```bash
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
echo 'vm.swappiness=10' | sudo tee /etc/sysctl.d/99-swap.conf
sudo sysctl --system
free -h
```

Install the memory limits from
`backend/config/systemd/memory-limits.conf.example` as a drop-in for each
backend unit (`rmirror` and `rmirror-staging`; the file explains the path).
The values are only suggestions: watch real usage first and tune them on the
server, then `sudo systemctl daemon-reload && sudo systemctl restart <unit>`.

## 7. External monitoring (open decisions)

- **Uptime check**: use an external uptime-monitoring service (it must run
  outside this server) that requests the public `/health` URL of production
  every minute or two and alerts by email or push after a couple of failures.
  Add staging as a second check if you want it. Which service and where alerts
  go is the owner's decision.
- **Backup heartbeat (optional)**: a dead-man's-switch style check that expects
  a ping after each nightly backup would also catch the timer never running.
  The script does not ping anything today; this is a decision for the owner.
- **Error reporting**: an error-tracking service for the backend, dashboard
  and agent is not set up. Open decision: which service, and whether to
  accept a new dependency and a third-party data processor.
