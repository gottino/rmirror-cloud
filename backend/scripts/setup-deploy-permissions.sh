#!/bin/bash
# Setup sudo permissions for the deploy user.
#
# IMPORTANT: this script must be re-run on the server, as root, every time it
# changes (merging it into main does NOT update /etc/sudoers.d/deploy).
#
# The generated sudoers file lists EXACT commands, no wildcards: sudo matches
# the full command line, so a command that is not on the list (a different
# flag, another unit name) prompts for a password and FAILS in CI. If a deploy
# workflow or script needs a new sudo command, add it to generate_sudoers()
# below, re-run this script on the server, and keep the line exact.
#
# Usage:
#   sudo ./setup-deploy-permissions.sh          install (as root)
#   ./setup-deploy-permissions.sh --print       print the sudoers text only

set -e

# Unit names the deploy user may manage: production and staging backends.
UNITS="rmirror rmirror-staging"

# Databases the deploy user may dump as postgres (pre-deploy dump, nightly
# backup, optional staging backup).
DATABASES="rmirror rmirror_staging"

generate_sudoers() {
    echo "# Managed by backend/scripts/setup-deploy-permissions.sh - do not edit by hand."
    echo "# Exact commands only; no wildcard arguments."
    echo ""
    echo "# Database dumps (pg_dump with a fixed database name)"
    for db in $DATABASES; do
        echo "deploy ALL=(postgres) NOPASSWD: /usr/bin/pg_dump $db"
        echo "deploy ALL=(postgres) NOPASSWD: /usr/bin/pg_dump -Fc $db"
    done
    for unit in $UNITS; do
        echo ""
        echo "# Service management: $unit"
        for dir in /usr/bin /bin; do
            echo "deploy ALL=(root) NOPASSWD: $dir/systemctl restart $unit"
            echo "deploy ALL=(root) NOPASSWD: $dir/systemctl status $unit"
            echo "deploy ALL=(root) NOPASSWD: $dir/systemctl is-active $unit"
            echo "deploy ALL=(root) NOPASSWD: $dir/systemctl is-active --quiet $unit"
        done
        echo "# Log viewing: $unit (one fixed form)"
        for dir in /usr/bin /bin; do
            echo "deploy ALL=(root) NOPASSWD: $dir/journalctl -u $unit --no-pager -n 200"
        done
    done
}

if [ "${1:-}" = "--print" ]; then
    generate_sudoers
    exit 0
fi

echo "=========================================="
echo "Setting up deploy user permissions"
echo "=========================================="
echo ""

# 1. Create backup directory
echo "1/3 Creating backup directory..."
mkdir -p /var/backups/rmirror
chown deploy:deploy /var/backups/rmirror
chmod 755 /var/backups/rmirror
echo "✅ Backup directory created: /var/backups/rmirror"
echo ""

# 2. Create sudoers configuration
echo "2/3 Configuring sudoers for deploy user..."
tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT
generate_sudoers > "$tmp"

# Validate BEFORE installing: an invalid file in /etc/sudoers.d breaks sudo for everyone.
if ! visudo -c -f "$tmp" > /dev/null 2>&1; then
    echo "❌ ERROR: generated sudoers is invalid, nothing installed!"
    exit 1
fi
# Sudoers files must be owned by root with mode 0440
install -m 0440 -o root -g root "$tmp" /etc/sudoers.d/deploy
echo "✅ Sudoers configuration created"
echo ""

# 3. Verify configuration
echo "3/3 Verifying configuration..."

# Test sudoers syntax
if visudo -c -f /etc/sudoers.d/deploy > /dev/null 2>&1; then
    echo "✅ Sudoers syntax is valid"
else
    echo "❌ ERROR: Sudoers syntax is invalid!"
    exit 1
fi

# Test permissions (if running as root, test as deploy user)
if [ "$EUID" -eq 0 ]; then
    echo ""
    echo "Testing deploy user permissions..."

    # Test systemctl
    if sudo -u deploy sudo -n systemctl status rmirror > /dev/null 2>&1; then
        echo "✅ systemctl permissions OK"
    else
        echo "⚠️  Could not test systemctl (service may not exist yet)"
    fi

    # Test pg_dump
    if sudo -u deploy sudo -n -u postgres -l /usr/bin/pg_dump rmirror > /dev/null 2>&1; then
        echo "✅ pg_dump permissions OK"
    else
        echo "❌ pg_dump permissions FAILED"
    fi

    # Test backup directory
    if sudo -u deploy touch /var/backups/rmirror/test_file && sudo -u deploy rm /var/backups/rmirror/test_file; then
        echo "✅ Backup directory permissions OK"
    else
        echo "❌ Backup directory permissions FAILED"
    fi
fi

echo ""
echo "=========================================="
echo "✅ Setup Complete!"
echo "=========================================="
echo ""
echo "The deploy user can now:"
echo "  • Create database backups in /var/backups/rmirror"
echo "  • Restart/status-check the rmirror and rmirror-staging services"
echo "  • View their logs (journalctl -u <unit> --no-pager -n 200)"
echo ""
echo "Test the deployment:"
echo "  sudo -u deploy /var/www/rmirror-cloud/backend/scripts/deploy.sh"
echo ""
