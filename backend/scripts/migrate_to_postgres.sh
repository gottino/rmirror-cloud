#!/bin/bash
set -e

# Fully automated PostgreSQL migration for rMirror Cloud
# This script handles everything: setup, migration, and service restart
# Run with: sudo -E ./scripts/migrate_to_postgres.sh

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
BACKEND_DIR="/var/www/rmirror-cloud/backend"
DB_NAME="rmirror"
DB_USER="rmirror"
SQLITE_DB="$BACKEND_DIR/rmirror.db"
ENV_FILE="$BACKEND_DIR/.env"

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}✗ Please run with sudo: sudo -E ./scripts/migrate_to_postgres.sh${NC}"
    exit 1
fi

# Check if we're in the right directory
if [ ! -f "$SQLITE_DB" ]; then
    echo -e "${RED}✗ SQLite database not found at $SQLITE_DB${NC}"
    echo "Please run this script from the backend directory"
    exit 1
fi

echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   rMirror Cloud - PostgreSQL Migration (Automated)        ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${YELLOW}This script will:${NC}"
echo "  1. Create PostgreSQL database and user"
echo "  2. Backup your current SQLite database"
echo "  3. Update .env with PostgreSQL connection"
echo "  4. Run database migrations"
echo "  5. Migrate all data from SQLite to PostgreSQL"
echo "  6. Restart the rMirror service"
echo ""
echo -e "${YELLOW}⚠️  Estimated downtime: 5-10 minutes${NC}"
echo ""
read -p "Continue with migration? (yes/no): " -r
echo
if [[ ! $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
    echo -e "${YELLOW}Migration cancelled${NC}"
    exit 0
fi

echo ""
echo -e "${BLUE}═══ Step 1/7: Checking prerequisites ═══${NC}"

# Check if PostgreSQL is running
if ! systemctl is-active --quiet postgresql; then
    echo -e "${RED}✗ PostgreSQL is not running${NC}"
    echo "Starting PostgreSQL..."
    systemctl start postgresql
fi
echo -e "${GREEN}✓ PostgreSQL is running${NC}"

# Set Poetry path (it's in deploy user's home)
POETRY_PATH="/home/deploy/.local/bin/poetry"
if [ ! -f "$POETRY_PATH" ]; then
    echo -e "${RED}✗ Poetry not found at $POETRY_PATH${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Poetry is available${NC}"

echo ""
echo -e "${BLUE}═══ Step 2/7: Creating PostgreSQL database ═══${NC}"

# Generate secure password
DB_PASSWORD=$(openssl rand -base64 32 | tr -d '/+=' | head -c 32)
echo -e "${GREEN}✓ Generated secure password${NC}"

# Save password to file (for reference)
echo "$DB_PASSWORD" > "$BACKEND_DIR/.postgres_password"
chmod 600 "$BACKEND_DIR/.postgres_password"
echo -e "${GREEN}✓ Password saved to .postgres_password${NC}"

# Create database and user
sudo -u postgres psql <<EOF 2>&1 | grep -v "already exists" || true
-- Create user if not exists
DO \$\$
BEGIN
   IF NOT EXISTS (SELECT FROM pg_user WHERE usename = '$DB_USER') THEN
      CREATE USER $DB_USER WITH PASSWORD '$DB_PASSWORD';
      RAISE NOTICE 'Created user $DB_USER';
   ELSE
      ALTER USER $DB_USER WITH PASSWORD '$DB_PASSWORD';
      RAISE NOTICE 'Updated password for user $DB_USER';
   END IF;
END
\$\$;

-- Create database if not exists
SELECT 'CREATE DATABASE $DB_NAME OWNER $DB_USER'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '$DB_NAME')\gexec

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;

-- Connect to database and grant schema privileges
\c $DB_NAME

GRANT ALL ON SCHEMA public TO $DB_USER;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO $DB_USER;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO $DB_USER;

-- Set default privileges
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO $DB_USER;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO $DB_USER;
EOF

echo -e "${GREEN}✓ PostgreSQL database and user created/updated${NC}"

echo ""
echo -e "${BLUE}═══ Step 3/7: Backing up SQLite database ═══${NC}"

BACKUP_FILE="${SQLITE_DB}.backup.$(date +%Y%m%d_%H%M%S)"
cp "$SQLITE_DB" "$BACKUP_FILE"
BACKUP_SIZE=$(ls -lh "$BACKUP_FILE" | awk '{print $5}')
echo -e "${GREEN}✓ Backup created: $(basename $BACKUP_FILE) ($BACKUP_SIZE)${NC}"

echo ""
echo -e "${BLUE}═══ Step 4/7: Updating .env configuration ═══${NC}"

# Backup current .env
cp "$ENV_FILE" "${ENV_FILE}.backup.$(date +%Y%m%d_%H%M%S)"
echo -e "${GREEN}✓ Backed up current .env${NC}"

# Create PostgreSQL connection URL
POSTGRES_URL="postgresql://$DB_USER:$DB_PASSWORD@localhost:5432/$DB_NAME"

# Update DATABASE_URL in .env
if grep -q "^DATABASE_URL=" "$ENV_FILE"; then
    # Replace existing DATABASE_URL
    sed -i.tmp "s|^DATABASE_URL=.*|DATABASE_URL=$POSTGRES_URL|" "$ENV_FILE"
    rm -f "${ENV_FILE}.tmp"
    echo -e "${GREEN}✓ Updated DATABASE_URL in .env${NC}"
else
    # Add DATABASE_URL
    echo "DATABASE_URL=$POSTGRES_URL" >> "$ENV_FILE"
    echo -e "${GREEN}✓ Added DATABASE_URL to .env${NC}"
fi

# Ensure DEBUG is not set to true in production
if grep -q "^DEBUG=true" "$ENV_FILE"; then
    sed -i.tmp "s|^DEBUG=true|DEBUG=false|" "$ENV_FILE"
    rm -f "${ENV_FILE}.tmp"
    echo -e "${YELLOW}⚠️  Set DEBUG=false for production${NC}"
fi

echo ""
echo -e "${BLUE}═══ Step 5/7: Running database migrations ═══${NC}"

# Stop service before migration
echo "Stopping rmirror service..."
systemctl stop rmirror.service
echo -e "${GREEN}✓ Service stopped${NC}"

# Run Alembic migrations as deploy user
echo "Running Alembic migrations..."
sudo -u deploy bash -c "cd $BACKEND_DIR && $POETRY_PATH run alembic upgrade head"
echo -e "${GREEN}✓ Database schema created${NC}"

echo ""
echo -e "${BLUE}═══ Step 6/7: Migrating data from SQLite to PostgreSQL ═══${NC}"

# Run migration script as deploy user
sudo -u deploy bash -c "cd $BACKEND_DIR && $POETRY_PATH run python scripts/migrate_sqlite_to_postgres.py --sqlite-path $SQLITE_DB --postgres-url '$POSTGRES_URL'"

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Data migration completed successfully${NC}"
else
    echo -e "${RED}✗ Data migration failed${NC}"
    echo "Rolling back to SQLite..."

    # Restore SQLite config
    cp "${ENV_FILE}.backup."* "$ENV_FILE" 2>/dev/null || true

    # Start service with SQLite
    systemctl start rmirror.service

    echo -e "${YELLOW}Rolled back to SQLite. Service restarted.${NC}"
    exit 1
fi

echo ""
echo -e "${BLUE}═══ Step 7/7: Starting service ═══${NC}"

# Start service
systemctl start rmirror.service

# Wait a moment for service to start
sleep 3

# Check service status
if systemctl is-active --quiet rmirror.service; then
    echo -e "${GREEN}✓ Service started successfully${NC}"
else
    echo -e "${RED}✗ Service failed to start${NC}"
    echo "Check logs with: sudo journalctl -u rmirror.service -n 50"
    exit 1
fi

echo ""
echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║   ✓ Migration completed successfully!                     ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${BLUE}Connection details:${NC}"
echo "  Database: $DB_NAME"
echo "  User: $DB_USER"
echo "  Password: (saved in .postgres_password)"
echo ""
echo -e "${BLUE}Next steps:${NC}"
echo "  1. Test the application: curl https://rmirror.io/health"
echo "  2. Check the dashboard loads and shows notebooks"
echo "  3. Monitor logs: sudo journalctl -u rmirror.service -f"
echo ""
echo -e "${BLUE}Backup files:${NC}"
echo "  SQLite backup: $(basename $BACKUP_FILE)"
echo "  .env backup: $(ls -t ${ENV_FILE}.backup.* | head -1 | xargs basename)"
echo ""
echo -e "${YELLOW}⚠️  Keep backups for at least 7 days before deleting${NC}"
echo ""
