#!/bin/bash
# rMirror Cloud - Production Deployment Script
# This script should be placed on the server at /var/www/rmirror-cloud/deploy.sh

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
APP_DIR="/var/www/rmirror-cloud/backend"
SERVICE_NAME="rmirror"
BACKUP_DIR="/var/backups/rmirror"
BRANCH="${1:-main}"  # Default to main branch, or use first argument

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}🚀 rMirror Cloud Deployment${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Check if running as deploy user
if [ "$USER" != "deploy" ]; then
    echo -e "${YELLOW}⚠️  Warning: Should be run as 'deploy' user${NC}"
    echo -e "${YELLOW}   Switching to deploy user...${NC}"
    sudo -u deploy bash "$0" "$@"
    exit $?
fi

# Navigate to app directory
cd "$APP_DIR" || { echo -e "${RED}❌ Failed to cd to $APP_DIR${NC}"; exit 1; }

echo -e "${BLUE}📂 Current directory: $(pwd)${NC}"
echo -e "${BLUE}🔀 Deploying branch: $BRANCH${NC}"
echo ""

# 1. Backup database
echo -e "${YELLOW}1/8 Creating database backup...${NC}"
mkdir -p "$BACKUP_DIR"
BACKUP_FILE="$BACKUP_DIR/rmirror_$(date +%Y%m%d_%H%M%S).sql.gz"
sudo -u postgres pg_dump rmirror | gzip > "$BACKUP_FILE"
echo -e "${GREEN}✅ Database backed up to: $BACKUP_FILE${NC}"
echo ""

# 2. Pull latest code
echo -e "${YELLOW}2/8 Pulling latest code from git...${NC}"
git fetch origin
CURRENT_COMMIT=$(git rev-parse HEAD)
echo -e "${BLUE}   Current commit: ${CURRENT_COMMIT:0:7}${NC}"

git checkout "$BRANCH"
git pull origin "$BRANCH"

NEW_COMMIT=$(git rev-parse HEAD)
echo -e "${BLUE}   New commit: ${NEW_COMMIT:0:7}${NC}"

if [ "$CURRENT_COMMIT" = "$NEW_COMMIT" ]; then
    echo -e "${GREEN}✅ Already up to date (no changes)${NC}"
else
    echo -e "${GREEN}✅ Updated from ${CURRENT_COMMIT:0:7} to ${NEW_COMMIT:0:7}${NC}"
fi
echo ""

# 3. Install/update dependencies
echo -e "${YELLOW}3/8 Installing dependencies...${NC}"
poetry install --no-dev --no-root --no-interaction
echo -e "${GREEN}✅ Dependencies installed${NC}"
echo ""

# 4. Run database migrations
echo -e "${YELLOW}4/8 Running database migrations...${NC}"
poetry run alembic upgrade head
echo -e "${GREEN}✅ Migrations complete${NC}"
echo ""

# 5. Check configuration
echo -e "${YELLOW}5/8 Checking configuration...${NC}"
if [ ! -f .env ]; then
    echo -e "${RED}❌ Error: .env file not found!${NC}"
    exit 1
fi

# Verify critical env vars
if ! grep -q "POSTGRES_USER" .env || ! grep -q "CLAUDE_API_KEY" .env; then
    echo -e "${RED}❌ Error: Missing critical environment variables!${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Configuration OK${NC}"
echo ""

# 6. Run tests (optional)
echo -e "${YELLOW}6/8 Running tests...${NC}"
if [ -d "tests" ]; then
    poetry run pytest --maxfail=1 --disable-warnings -q || {
        echo -e "${RED}❌ Tests failed! Aborting deployment.${NC}"
        exit 1
    }
    echo -e "${GREEN}✅ Tests passed${NC}"
else
    echo -e "${YELLOW}⚠️  No tests found, skipping${NC}"
fi
echo ""

# 7. Restart application
echo -e "${YELLOW}7/8 Restarting application...${NC}"
sudo systemctl restart "$SERVICE_NAME"

# Wait for service to start
sleep 2

# Check if service is running
if sudo systemctl is-active --quiet "$SERVICE_NAME"; then
    echo -e "${GREEN}✅ Service restarted successfully${NC}"
else
    echo -e "${RED}❌ Service failed to start!${NC}"
    echo -e "${RED}   Checking logs...${NC}"
    sudo journalctl -u "$SERVICE_NAME" -n 20 --no-pager
    exit 1
fi
echo ""

# 8. Health check
echo -e "${YELLOW}8/8 Running health check...${NC}"
sleep 3  # Give the app time to fully start

HEALTH_CHECK=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health || echo "000")
if [ "$HEALTH_CHECK" = "200" ]; then
    echo -e "${GREEN}✅ Health check passed (HTTP $HEALTH_CHECK)${NC}"
else
    echo -e "${RED}❌ Health check failed (HTTP $HEALTH_CHECK)${NC}"
    echo -e "${RED}   Check application logs:${NC}"
    echo -e "${RED}   sudo journalctl -u $SERVICE_NAME -f${NC}"
    exit 1
fi
echo ""

# Success summary
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}✅ Deployment Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${BLUE}📊 Deployment Summary:${NC}"
echo -e "   • Branch: $BRANCH"
echo -e "   • Commit: ${NEW_COMMIT:0:7}"
echo -e "   • Backup: $BACKUP_FILE"
echo -e "   • Service: $SERVICE_NAME (running)"
echo -e "   • Health: OK"
echo ""
echo -e "${BLUE}🔍 Useful commands:${NC}"
echo -e "   • View logs: ${YELLOW}sudo journalctl -u $SERVICE_NAME -f${NC}"
echo -e "   • Service status: ${YELLOW}sudo systemctl status $SERVICE_NAME${NC}"
echo -e "   • Rollback: ${YELLOW}git checkout $CURRENT_COMMIT && ./deploy.sh${NC}"
echo ""
