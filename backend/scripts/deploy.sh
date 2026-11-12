#!/bin/bash
# rMirror Cloud - Production Deployment Script
#
# Usage: deploy.sh <commit-sha>        (or DEPLOY_SHA=<commit-sha> deploy.sh)
#
# Deploys exactly the given commit (it must be on origin/main) into the
# checkout at /var/www/rmirror-cloud. deploy-production.yml runs the copy of
# this script from the commit it deploys. Without a SHA (manual run) it
# deploys the current origin/main and prints a warning.
#
# Order: resolve commit -> config check -> DB backup -> checkout -> deps ->
# config check (new code) -> migrations -> restart -> health check -> dashboard.
# If anything fails after the checkout, the previous commit is checked out
# again, reinstalled and restarted, and the script exits non-zero. Migrations
# are NOT undone automatically; the script prints the backup to restore from.
#
# Every sudo command here must match a line printed by
# `setup-deploy-permissions.sh --print` exactly.

set -eo pipefail  # pipefail: a failing pg_dump/git show must not be hidden by the pipe

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration. The DEPLOY_* overrides exist for tests/test_deploy_script.py;
# the defaults are the production values.
APP_DIR="${DEPLOY_APP_DIR:-/var/www/rmirror-cloud/backend}"
DASHBOARD_DIR="${DEPLOY_DASHBOARD_DIR:-/var/www/rmirror-cloud/dashboard}"
BACKUP_DIR="${DEPLOY_BACKUP_DIR:-/var/backups/rmirror}"
HEALTH_URL="${DEPLOY_HEALTH_URL:-http://localhost:8000/health}"
SERVICE_NAME="rmirror"  # fixed: must match the sudoers file
TARGET_ARG="${1:-${DEPLOY_SHA:-}}"

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
REPO_DIR="$(git rev-parse --show-toplevel)"

echo -e "${BLUE}📂 Current directory: $(pwd)${NC}"
echo ""

# Find poetry (check common locations)
if command -v poetry &> /dev/null; then
    POETRY="poetry"
elif [ -f "/home/deploy/.local/bin/poetry" ]; then
    POETRY="/home/deploy/.local/bin/poetry"
elif [ -f "$HOME/.local/bin/poetry" ]; then
    POETRY="$HOME/.local/bin/poetry"
elif [ -f "/root/.local/bin/poetry" ]; then
    POETRY="/root/.local/bin/poetry"
else
    echo -e "${RED}❌ Poetry not found! Install it first:${NC}"
    echo -e "${RED}   curl -sSL https://install.python-poetry.org | python3 -${NC}"
    exit 1
fi
echo -e "${BLUE}📦 Using poetry: $POETRY${NC}"
echo ""

# Poll the backend health endpoint for up to 60 seconds.
wait_healthy() {
    local code="000"
    for i in $(seq 1 30); do
        sleep 2
        code=$(curl -s -o /dev/null -w "%{http_code}" "$HEALTH_URL" 2>/dev/null || true)
        if [ "$code" = "200" ]; then
            echo -e "${GREEN}✅ Backend health check passed (HTTP $code)${NC}"
            return 0
        fi
        echo -e "${YELLOW}   Waiting for backend... (attempt $i/30, HTTP ${code:-000})${NC}"
    done
    echo -e "${RED}❌ Backend health check failed after 60s (HTTP ${code:-000})${NC}"
    return 1
}

CODE_CHANGED=0
MIGRATIONS_RAN=0
BACKUP_FILE=""

# Called on any failure after the checkout started: restore the previous
# commit, reinstall, restart, and exit non-zero. Never runs alembic downgrade.
rollback() {
    local reason="$1"
    local ok=1
    echo ""
    echo -e "${RED}❌ Deploy failed: $reason${NC}"
    if [ "$CODE_CHANGED" = "1" ]; then
        echo -e "${YELLOW}↩️  Rolling back code to ${PREVIOUS_COMMIT:0:7}...${NC}"
        git checkout --force --detach "$PREVIOUS_COMMIT" || ok=0
        if [ "$ok" = "1" ]; then
            $POETRY install --without dev --no-root --no-interaction || ok=0
            echo "$PREVIOUS_COMMIT" > "$APP_DIR/.deploy-commit" || true
            sudo systemctl restart "$SERVICE_NAME" || ok=0
        fi
        if [ "$ok" = "1" ] && wait_healthy; then
            echo -e "${YELLOW}↩️  Rolled back to ${PREVIOUS_COMMIT:0:7}; backend is healthy on the previous code.${NC}"
        else
            echo -e "${RED}❌ ROLLBACK DID NOT COMPLETE. Check the service by hand:${NC}"
            echo -e "${RED}   sudo journalctl -u $SERVICE_NAME --no-pager -n 200${NC}"
        fi
    fi
    if [ "$MIGRATIONS_RAN" = "1" ]; then
        echo ""
        echo -e "${RED}========================================${NC}"
        echo -e "${RED}⚠️  DATABASE MIGRATIONS RAN (or were attempted) during this deploy.${NC}"
        echo -e "${RED}   The database schema may now be AHEAD of the running code.${NC}"
        echo -e "${RED}   Migrations were NOT reverted automatically.${NC}"
        echo -e "${RED}   Pre-deploy dump: $BACKUP_FILE${NC}"
        echo -e "${RED}   Decide by hand: fix forward, or restore that dump.${NC}"
        echo -e "${RED}========================================${NC}"
    fi
    exit 1
}

# 1. Resolve the commit to deploy
echo -e "${YELLOW}1/9 Fetching code and resolving the commit to deploy...${NC}"
git fetch origin
case "$TARGET_ARG" in
    ""|main|origin/main)
        echo -e "${YELLOW}⚠️  No commit SHA given: deploying the current origin/main.${NC}"
        echo -e "${YELLOW}   Pass the SHA (deploy.sh <sha>) to deploy exactly the tested commit.${NC}"
        TARGET_COMMIT=$(git rev-parse --verify "origin/main^{commit}")
        ;;
    *)
        if ! [[ "$TARGET_ARG" =~ ^[0-9a-f]{7,40}$ ]]; then
            echo -e "${RED}❌ Not a commit SHA: '$TARGET_ARG'. Pass a commit SHA from main.${NC}"
            exit 1
        fi
        if ! TARGET_COMMIT=$(git rev-parse --verify --quiet "${TARGET_ARG}^{commit}"); then
            echo -e "${RED}❌ Commit $TARGET_ARG does not exist (after git fetch). Refusing to deploy.${NC}"
            exit 1
        fi
        ;;
esac
if ! git merge-base --is-ancestor "$TARGET_COMMIT" origin/main; then
    echo -e "${RED}❌ Commit ${TARGET_COMMIT:0:7} is not on origin/main. Refusing to deploy.${NC}"
    exit 1
fi
PREVIOUS_COMMIT=$(git rev-parse HEAD)
echo -e "${BLUE}   Current commit: ${PREVIOUS_COMMIT:0:7}${NC}"
echo -e "${BLUE}   Target commit:  ${TARGET_COMMIT:0:7}${NC}"
echo ""

# 2. Check configuration BEFORE changing anything. Runs the target commit's
# check script against the current code's settings loader and .env.
echo -e "${YELLOW}2/9 Checking configuration...${NC}"
if [ ! -f .env ]; then
    echo -e "${RED}❌ Error: .env file not found!${NC}"
    exit 1
fi
CHECK_SCRIPT="$TARGET_COMMIT:backend/scripts/check_config.py"
if ! git cat-file -e "$CHECK_SCRIPT" 2>/dev/null; then
    CHECK_SCRIPT="HEAD:backend/scripts/check_config.py"
fi
if ! git show "$CHECK_SCRIPT" | $POETRY run python -; then
    echo -e "${RED}❌ Configuration check failed (missing names above). Nothing was changed.${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Configuration OK${NC}"
echo ""

# 3. Backup database
echo -e "${YELLOW}3/9 Creating database backup...${NC}"
mkdir -p "$BACKUP_DIR"
BACKUP_FILE="$BACKUP_DIR/rmirror_$(date +%Y%m%d_%H%M%S).sql.gz"
if ! sudo -u postgres pg_dump rmirror | gzip > "$BACKUP_FILE"; then
    rm -f "$BACKUP_FILE"
    echo -e "${RED}❌ Database backup failed; aborting deploy${NC}"
    exit 1
fi
BACKUP_SIZE=$(stat -c %s "$BACKUP_FILE")
if [ "$BACKUP_SIZE" -lt 1024 ]; then
    rm -f "$BACKUP_FILE"
    echo -e "${RED}❌ Database backup is empty or too small ($BACKUP_SIZE bytes); aborting deploy${NC}"
    exit 1
fi
find "$BACKUP_DIR" -maxdepth 1 -name 'rmirror_*.sql.gz' -mtime +14 -delete
echo -e "${GREEN}✅ Database backed up to: $BACKUP_FILE${NC}"
echo ""

# 4. Check out the target commit (detached; discards local edits and
# untracked files like the workflow's old reset --hard + clean did)
echo -e "${YELLOW}4/9 Checking out ${TARGET_COMMIT:0:7}...${NC}"
CODE_CHANGED=1
git merge --abort > /dev/null 2>&1 || true
git checkout --force --detach "$TARGET_COMMIT" || rollback "git checkout failed"
git -C "$REPO_DIR" clean -fd || rollback "git clean failed"
NEW_COMMIT=$(git rev-parse HEAD)
if [ "$PREVIOUS_COMMIT" = "$NEW_COMMIT" ]; then
    echo -e "${GREEN}✅ Already at ${NEW_COMMIT:0:7} (no code changes)${NC}"
else
    echo -e "${GREEN}✅ Updated from ${PREVIOUS_COMMIT:0:7} to ${NEW_COMMIT:0:7}${NC}"
fi
echo ""

# 5. Install/update dependencies
echo -e "${YELLOW}5/9 Installing dependencies...${NC}"
$POETRY install --without dev --no-root --no-interaction || rollback "dependency install failed"
echo -e "${GREEN}✅ Dependencies installed${NC}"
echo ""

# 6. Check configuration again, with the settings of the code being deployed
echo -e "${YELLOW}6/9 Checking configuration against the new code...${NC}"
$POETRY run python scripts/check_config.py || rollback "configuration check failed for the new code"
echo ""

# 7. Run database migrations
echo -e "${YELLOW}7/9 Running database migrations...${NC}"
MIGRATIONS_RAN=1
$POETRY run alembic upgrade head || rollback "database migration failed"
echo -e "${GREEN}✅ Migrations complete${NC}"
echo ""

# 8. Restart application and wait for it to be healthy
echo -e "${YELLOW}8/9 Restarting application...${NC}"
echo "$NEW_COMMIT" > "$APP_DIR/.deploy-commit" || rollback "could not write $APP_DIR/.deploy-commit"
sudo systemctl restart "$SERVICE_NAME" || rollback "service restart failed"
sleep 2
if ! sudo systemctl is-active --quiet "$SERVICE_NAME"; then
    echo -e "${RED}❌ Service failed to start! Checking logs...${NC}"
    sudo journalctl -u "$SERVICE_NAME" --no-pager -n 200 || true
    rollback "service did not start"
fi
if ! wait_healthy; then
    sudo journalctl -u "$SERVICE_NAME" --no-pager -n 200 || true
    rollback "backend health check failed"
fi
# The backend is live on the new code; failures past this point do not roll it back.
CODE_CHANGED=0
MIGRATIONS_RAN=0
echo ""

# 9. Deploy dashboard
echo -e "${YELLOW}9/9 Deploying Next.js dashboard...${NC}"
if [ -d "$DASHBOARD_DIR" ]; then
    cd "$DASHBOARD_DIR" || { echo -e "${RED}❌ Failed to cd to $DASHBOARD_DIR${NC}"; exit 1; }

    # Load nvm (Node Version Manager). --no-use: when nvm's `default` alias
    # points at a version that isn't installed, sourcing nvm.sh returns 3 and
    # `set -e` silently aborted the deploy here (2026-11-10). Use the newest
    # installed Node directly instead.
    export NVM_DIR="$HOME/.nvm"
    if [ -s "$NVM_DIR/nvm.sh" ]; then
        \. "$NVM_DIR/nvm.sh" --no-use || true
    else
        echo -e "${RED}❌ nvm not found! Install it first:${NC}"
        echo -e "${RED}   curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash${NC}"
        echo -e "${RED}   Then run: nvm install --lts${NC}"
        exit 1
    fi
    export PATH="$NVM_DIR/versions/node/$(ls "$NVM_DIR/versions/node" 2>/dev/null | sort -V | tail -1)/bin:$PATH"
    for cmd in node npm pm2; do
        if ! command -v "$cmd" > /dev/null; then
            echo -e "${RED}❌ $cmd not found in $NVM_DIR/versions/node/*/bin${NC}"
            exit 1
        fi
    done
    echo -e "${BLUE}   Using Node.js $(node --version), npm $(npm --version), pm2 $(pm2 --version 2>/dev/null | tail -1)${NC}"

    DASHBOARD_TARBALL="/tmp/dashboard-production.tgz"
    if [ -f "$DASHBOARD_TARBALL" ]; then
        # Prebuilt in GitHub Actions (deploy-production.yml). Building here runs
        # the server out of memory.
        echo -e "${BLUE}   Installing prebuilt dashboard...${NC}"
        "$DASHBOARD_DIR/deploy/install-release.sh" "$DASHBOARD_TARBALL" \
            "$HOME/rmirror-releases/dashboard-production" \
            "$DASHBOARD_DIR/.env" \
            rmirror-dashboard 3000 \
            "$DASHBOARD_DIR"
        echo -e "${GREEN}✅ Dashboard deployed${NC}"
    elif [ -f "package.json" ]; then
        echo -e "${YELLOW}⚠️  No prebuilt dashboard at $DASHBOARD_TARBALL; building on the server.${NC}"
        echo -e "${YELLOW}   This needs ~1.5 GB free memory; prefer the GitHub Actions deploy.${NC}"
        echo -e "${BLUE}   Installing npm dependencies...${NC}"
        npm install

        # Build Next.js for production
        echo -e "${BLUE}   Building Next.js app...${NC}"
        npm run build

        # Replace rather than restart: the running process may be a prebuilt
        # standalone release, which a restart would bring back instead of this build
        echo -e "${BLUE}   Starting dashboard with PM2...${NC}"
        pm2 delete rmirror-dashboard 2>/dev/null || true
        cd "$DASHBOARD_DIR"
        pm2 start npm --name "rmirror-dashboard" -- start
        pm2 save

        echo -e "${GREEN}✅ Dashboard deployed${NC}"
    else
        echo -e "${YELLOW}⚠️  No package.json found, skipping dashboard${NC}"
    fi

    cd "$APP_DIR"  # Return to backend directory
else
    echo -e "${YELLOW}⚠️  Dashboard directory not found, skipping${NC}"
fi

# Check dashboard health
DASHBOARD_HEALTH=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:3000 || echo "000")
if [ "$DASHBOARD_HEALTH" = "200" ] || [ "$DASHBOARD_HEALTH" = "307" ]; then
    echo -e "${GREEN}✅ Dashboard health check passed (HTTP $DASHBOARD_HEALTH)${NC}"
else
    echo -e "${YELLOW}⚠️  Dashboard health check: HTTP $DASHBOARD_HEALTH${NC}"
fi
echo ""

# Success summary
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}✅ Deployment Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${BLUE}📊 Deployment Summary:${NC}"
echo -e "   • Commit: ${NEW_COMMIT:0:7} (previous: ${PREVIOUS_COMMIT:0:7})"
echo -e "   • Backup: $BACKUP_FILE"
echo -e "   • Backend: $SERVICE_NAME (running)"
echo -e "   • Dashboard: PM2 (running)"
echo -e "   • Health: OK"
echo ""
echo -e "${BLUE}🔍 Useful commands:${NC}"
echo -e "   • Backend logs: ${YELLOW}sudo journalctl -u $SERVICE_NAME -f${NC}"
echo -e "   • Dashboard logs: ${YELLOW}pm2 logs rmirror-dashboard${NC}"
echo -e "   • Service status: ${YELLOW}sudo systemctl status $SERVICE_NAME${NC}"
echo -e "   • Dashboard status: ${YELLOW}pm2 status rmirror-dashboard${NC}"
echo -e "   • Code rollback: ${YELLOW}backend/scripts/deploy.sh $PREVIOUS_COMMIT${NC} (does not undo migrations)"
echo ""
