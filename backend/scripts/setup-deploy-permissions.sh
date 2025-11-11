#!/bin/bash
# Setup sudo permissions for deploy user
# Run this once on the server as root or with sudo

set -e

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
cat > /etc/sudoers.d/deploy << 'EOF'
# Allow deploy user to run deployment commands without password
# Database backup
deploy ALL=(postgres) NOPASSWD: /usr/bin/pg_dump

# Service management (wildcard allows any flags/arguments)
deploy ALL=(root) NOPASSWD: /usr/bin/systemctl * rmirror
deploy ALL=(root) NOPASSWD: /bin/systemctl * rmirror

# Log viewing (wildcard allows any arguments)
deploy ALL=(root) NOPASSWD: /usr/bin/journalctl *
EOF

# Set proper permissions on sudoers file (must be 0440)
chmod 0440 /etc/sudoers.d/deploy
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
    if sudo -u deploy sudo -n -u postgres pg_dump --version > /dev/null 2>&1; then
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
echo "  • Restart the rmirror service"
echo "  • View service logs"
echo ""
echo "Test the deployment:"
echo "  sudo -u deploy /var/www/rmirror-cloud/backend/scripts/deploy.sh"
echo ""
