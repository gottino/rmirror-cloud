#!/usr/bin/env bash
# rMirror Cloud - nightly database backup.
#
# Dumps one PostgreSQL database in custom format (pg_dump -Fc), checks that the
# dump is not empty, keeps the newest 7 local dumps and, when configured,
# uploads the dump to an S3-compatible bucket with the AWS CLI.
#
# Configuration (environment variables, normally from the systemd
# EnvironmentFile; see docs/deployment/backups.md):
#   BACKUP_DB_NAME        required  database to dump
#   BACKUP_DIR            optional  local directory (default /var/backups/rmirror/nightly)
#   BACKUP_PG_SUDO_USER   optional  run pg_dump through "sudo -n -u <user>"
#   BACKUP_KEEP           optional  local copies to keep (default 7)
#   BACKUP_MIN_BYTES      optional  smallest acceptable dump size (default 1024)
#   BACKUP_S3_BUCKET, BACKUP_S3_ENDPOINT, BACKUP_S3_ACCESS_KEY, BACKUP_S3_SECRET_KEY
#                         optional  all four set => upload with "aws s3 cp --endpoint-url"
#
# Exits non-zero on any failure so that systemd records the unit as failed.
# Secrets are never printed.

set -euo pipefail

log() { echo "backup-db: $*"; }
die() { echo "backup-db: ERROR: $*" >&2; exit 1; }

DB_NAME="${BACKUP_DB_NAME:-}"
[ -n "$DB_NAME" ] || die "BACKUP_DB_NAME is not set"

BACKUP_DIR="${BACKUP_DIR:-/var/backups/rmirror/nightly}"
KEEP="${BACKUP_KEEP:-7}"
MIN_BYTES="${BACKUP_MIN_BYTES:-1024}"
case "$KEEP" in ''|*[!0-9]*) die "BACKUP_KEEP must be a positive integer" ;; esac
[ "$KEEP" -ge 1 ] || die "BACKUP_KEEP must be at least 1"
case "$MIN_BYTES" in ''|*[!0-9]*) die "BACKUP_MIN_BYTES must be an integer" ;; esac

# Decide up front whether an upload is wanted, so a missing CLI fails before dumping.
s3_set=0
for v in BACKUP_S3_BUCKET BACKUP_S3_ENDPOINT BACKUP_S3_ACCESS_KEY BACKUP_S3_SECRET_KEY; do
    [ -n "${!v:-}" ] && s3_set=$((s3_set + 1))
done
upload=0
if [ "$s3_set" -eq 4 ]; then
    upload=1
    command -v aws >/dev/null 2>&1 \
        || die "off-site upload is configured but the 'aws' CLI is not installed"
elif [ "$s3_set" -gt 0 ]; then
    die "off-site upload is partly configured: set all of BACKUP_S3_BUCKET, BACKUP_S3_ENDPOINT, BACKUP_S3_ACCESS_KEY, BACKUP_S3_SECRET_KEY or none"
else
    log "off-site upload not configured; keeping local copies only"
fi

mkdir -p "$BACKUP_DIR"
stamp="$(date +%Y%m%d_%H%M%S)"
final="$BACKUP_DIR/${DB_NAME}_${stamp}.dump"
partial="$final.partial"
trap 'rm -f "$partial"' EXIT

dump_cmd=(pg_dump -Fc "$DB_NAME")
if [ -n "${BACKUP_PG_SUDO_USER:-}" ]; then
    dump_cmd=(sudo -n -u "$BACKUP_PG_SUDO_USER" "${dump_cmd[@]}")
fi

log "dumping database '$DB_NAME'"
"${dump_cmd[@]}" > "$partial" || die "pg_dump failed"

size="$(stat -c %s "$partial")"
[ "$size" -ge "$MIN_BYTES" ] || die "dump is empty or too small ($size bytes, minimum $MIN_BYTES)"
mv "$partial" "$final"
log "wrote $final ($size bytes)"

# Keep the newest $KEEP local dumps of this database.
mapfile -t old < <(ls -1t "$BACKUP_DIR"/"${DB_NAME}"_*.dump 2>/dev/null | tail -n +"$((KEEP + 1))")
if [ "${#old[@]}" -gt 0 ]; then
    rm -f -- "${old[@]}"
    log "removed ${#old[@]} old local dump(s)"
fi

if [ "$upload" -eq 1 ]; then
    log "uploading to the configured bucket"
    AWS_ACCESS_KEY_ID="$BACKUP_S3_ACCESS_KEY" \
    AWS_SECRET_ACCESS_KEY="$BACKUP_S3_SECRET_KEY" \
    AWS_DEFAULT_REGION="${BACKUP_S3_REGION:-us-east-1}" \
        aws s3 cp --only-show-errors --endpoint-url "$BACKUP_S3_ENDPOINT" \
            "$final" "s3://${BACKUP_S3_BUCKET}/$(basename "$final")" \
        || die "upload failed"
    log "upload finished"
fi

log "done"
