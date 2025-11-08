#!/bin/bash
# rMirror Cloud - Remote Deployment Trigger
# This script runs on your LOCAL machine to trigger deployment on the server

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration (override with environment variables)
SERVER_HOST="${RMIRROR_SERVER_HOST:-167.235.74.51}"
SERVER_USER="${RMIRROR_SERVER_USER:-deploy}"
SERVER_PORT="${RMIRROR_SERVER_PORT:-22}"
BRANCH="${1:-main}"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}🚀 Remote Deployment Trigger${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Check if server is configured
if [ "$SERVER_HOST" = "YOUR_SERVER_IP" ]; then
    echo -e "${RED}❌ Server not configured!${NC}"
    echo ""
    echo "Please set your server details:"
    echo ""
    echo "  export RMIRROR_SERVER_HOST=167.235.74.51"
    echo "  export RMIRROR_SERVER_USER=deploy"
    echo ""
    echo "Or edit this script with your server IP"
    exit 1
fi

echo -e "${BLUE}📡 Server: $SERVER_USER@$SERVER_HOST${NC}"
echo -e "${BLUE}🔀 Branch: $BRANCH${NC}"
echo ""

# Confirm deployment
read -p "$(echo -e ${YELLOW}Deploy to production? [y/N]:${NC} )" -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${YELLOW}⚠️  Deployment cancelled${NC}"
    exit 0
fi
echo ""

# Push to git first
echo -e "${YELLOW}1/2 Pushing local changes to git...${NC}"
CURRENT_BRANCH=$(git branch --show-current)
if [ "$CURRENT_BRANCH" != "$BRANCH" ]; then
    echo -e "${YELLOW}⚠️  Warning: Currently on branch '$CURRENT_BRANCH', but deploying '$BRANCH'${NC}"
fi

if [ "$CURRENT_BRANCH" = "$BRANCH" ]; then
    if [[ -n $(git status -s) ]]; then
        echo -e "${YELLOW}⚠️  You have uncommitted changes:${NC}"
        git status -s
        echo ""
        read -p "$(echo -e ${YELLOW}Commit and push these changes? [y/N]:${NC} )" -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            read -p "$(echo -e ${YELLOW}Commit message:${NC} )" COMMIT_MSG
            git add -A
            git commit -m "$COMMIT_MSG"
        fi
    fi

    echo -e "${BLUE}   Pushing to origin/$BRANCH...${NC}"
    git push origin "$BRANCH"
    echo -e "${GREEN}✅ Git push complete${NC}"
else
    echo -e "${YELLOW}⚠️  Skipping git push (not on deployment branch)${NC}"
fi
echo ""

# Trigger remote deployment
echo -e "${YELLOW}2/2 Triggering remote deployment...${NC}"
echo ""

ssh -p "$SERVER_PORT" "$SERVER_USER@$SERVER_HOST" << ENDSSH
    cd /var/www/rmirror-cloud
    ./deploy.sh $BRANCH
ENDSSH

DEPLOY_STATUS=$?

echo ""
if [ $DEPLOY_STATUS -eq 0 ]; then
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}✅ Remote Deployment Complete!${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo ""
    echo -e "${BLUE}🔍 Check status:${NC}"
    echo -e "   ssh $SERVER_USER@$SERVER_HOST 'sudo systemctl status rmirror'"
    echo ""
    echo -e "${BLUE}📊 View logs:${NC}"
    echo -e "   ssh $SERVER_USER@$SERVER_HOST 'sudo journalctl -u rmirror -f'"
    echo ""
else
    echo -e "${RED}========================================${NC}"
    echo -e "${RED}❌ Deployment Failed!${NC}"
    echo -e "${RED}========================================${NC}"
    echo ""
    echo -e "${RED}Check server logs:${NC}"
    echo -e "   ssh $SERVER_USER@$SERVER_HOST 'sudo journalctl -u rmirror -n 50'"
    exit 1
fi
