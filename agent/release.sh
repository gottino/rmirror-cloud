#!/bin/bash
#
# Release script for rMirror Agent
#
# This script:
# 1. Uploads the DMG to Backblaze B2
# 2. Updates the dashboard download link
# 3. Commits and pushes the changes
#
# Prerequisites:
# - b2 CLI installed (brew install b2-tools)
# - b2 authorized (run: b2 account authorize)
# - DMG built and signed in dist/
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Get version from pyproject.toml
VERSION=$(grep '^version = ' pyproject.toml | sed 's/version = "\(.*\)"/\1/')
DMG_PATH="dist/rMirror-${VERSION}.dmg"
BUCKET_NAME="rmirror-downloads"
B2_PATH="releases/v${VERSION}/rMirror-${VERSION}.dmg"
DASHBOARD_FILE="../dashboard/app/dashboard/page.tsx"

echo -e "${GREEN}================================================${NC}"
echo -e "${GREEN}  Releasing rMirror Agent v${VERSION}${NC}"
echo -e "${GREEN}================================================${NC}"
echo ""

# Check prerequisites
echo -e "${YELLOW}→${NC} Checking prerequisites..."

if [ ! -f "$DMG_PATH" ]; then
    echo -e "${RED}✗${NC} DMG not found: $DMG_PATH"
    echo -e "   Run ./build_macos.sh first"
    exit 1
fi

if ! command -v b2 &> /dev/null; then
    echo -e "${RED}✗${NC} b2 CLI not installed"
    echo -e "   Run: brew install b2-tools"
    exit 1
fi

# Load B2 credentials from Keychain
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$SCRIPT_DIR/b2-keychain.sh" ]; then
    eval $("$SCRIPT_DIR/b2-keychain.sh" get 2>/dev/null) || true
fi

# Check b2 authorization (authorize if env vars are set but not yet authorized)
if ! b2 account get 2>/dev/null | grep -q "accountId"; then
    if [ -n "$B2_APPLICATION_KEY_ID" ] && [ -n "$B2_APPLICATION_KEY" ]; then
        echo -e "${YELLOW}→${NC} Authorizing with B2 using Keychain credentials..."
        b2 account authorize
    else
        echo -e "${RED}✗${NC} b2 not authorized and no Keychain credentials found"
        echo -e "   Run: ./b2-keychain.sh store"
        exit 1
    fi
fi

echo -e "${GREEN}✓${NC} All prerequisites met"
echo ""

# Step 1: Upload to Backblaze B2
echo -e "${YELLOW}→${NC} Uploading to Backblaze B2..."
echo -e "   Bucket: $BUCKET_NAME"
echo -e "   Path: $B2_PATH"

b2 file upload "$BUCKET_NAME" "$DMG_PATH" "$B2_PATH"

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓${NC} Upload complete"
else
    echo -e "${RED}✗${NC} Upload failed"
    exit 1
fi
echo ""

# Step 2: Generate and upload version.json for auto-update checking
echo -e "${YELLOW}→${NC} Uploading version manifest..."
DOWNLOAD_URL="https://f000.backblazeb2.com/file/${BUCKET_NAME}/releases/v${VERSION}/rMirror-${VERSION}.dmg"

cat > /tmp/version.json << EOF
{
  "version": "${VERSION}",
  "download_url": "${DOWNLOAD_URL}",
  "release_notes": "",
  "published_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "min_supported_version": "1.0.0"
}
EOF

b2 file upload "$BUCKET_NAME" /tmp/version.json "releases/latest/version.json"

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓${NC} Version manifest uploaded"
else
    echo -e "${RED}✗${NC} Version manifest upload failed"
    exit 1
fi
rm /tmp/version.json
echo ""

# Step 3: Update dashboard download link
echo -e "${YELLOW}→${NC} Updating dashboard download link..."

if [ ! -f "$DASHBOARD_FILE" ]; then
    echo -e "${RED}✗${NC} Dashboard file not found: $DASHBOARD_FILE"
    exit 1
fi

# Update the download URL in dashboard
sed -i '' "s|releases/v[0-9.]*\/rMirror-[0-9.]*.dmg|releases/v${VERSION}/rMirror-${VERSION}.dmg|g" "$DASHBOARD_FILE"

echo -e "${GREEN}✓${NC} Dashboard updated to v${VERSION}"
echo ""

# Step 4: Show diff and ask for confirmation
echo -e "${YELLOW}→${NC} Changes to commit:"
cd ..
git diff --stat dashboard/
echo ""
git diff dashboard/app/dashboard/page.tsx | head -20
echo ""

read -p "Commit and push these changes? [y/N] " -n 1 -r
echo ""

if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${YELLOW}→${NC} Committing changes..."
    git add dashboard/app/dashboard/page.tsx
    git commit -m "chore(dashboard): update agent download link to v${VERSION}

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"

    echo -e "${YELLOW}→${NC} Pushing to GitHub..."
    git push

    echo -e "${GREEN}✓${NC} Changes pushed"
else
    echo -e "${YELLOW}⚠${NC}  Skipped commit/push"
    echo -e "   Don't forget to commit the dashboard changes manually!"
fi
echo ""

# Summary
DOWNLOAD_URL="https://f000.backblazeb2.com/file/${BUCKET_NAME}/${B2_PATH}"
echo -e "${GREEN}================================================${NC}"
echo -e "${GREEN}  Release Complete!${NC}"
echo -e "${GREEN}================================================${NC}"
echo ""
echo -e "Version:  ${VERSION}"
echo -e "Download: ${DOWNLOAD_URL}"
echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo -e "1. Test download: curl -I '${DOWNLOAD_URL}'"
echo -e "2. Verify dashboard shows new version"
echo -e "3. Announce release if needed"
echo ""
