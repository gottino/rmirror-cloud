#!/bin/bash
#
# Setup notarization credentials for rMirror
#
# This script stores your Apple ID and app-specific password
# in the macOS keychain for use during notarization.
#

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}================================================${NC}"
echo -e "${GREEN}  rMirror Notarization Setup${NC}"
echo -e "${GREEN}================================================${NC}"
echo ""

# Team ID from certificate
TEAM_ID="2K34CUCVB2"

echo -e "${YELLOW}You will need:${NC}"
echo "1. Your Apple ID (email address)"
echo "2. An app-specific password for notarization"
echo ""
echo -e "${YELLOW}To create an app-specific password:${NC}"
echo "1. Go to https://appleid.apple.com"
echo "2. Sign in with your Apple ID"
echo "3. Go to 'Security' section"
echo "4. Under 'App-Specific Passwords', click 'Generate Password'"
echo "5. Enter 'rMirror Notarization' as the label"
echo "6. Copy the generated password (format: xxxx-xxxx-xxxx-xxxx)"
echo ""

read -p "Enter your Apple ID (email): " APPLE_ID
echo ""
read -s -p "Enter your app-specific password: " APP_PASSWORD
echo ""
echo ""

echo -e "${YELLOW}→${NC} Storing credentials in keychain..."

# Store credentials using notarytool
xcrun notarytool store-credentials "AC_PASSWORD" \
    --apple-id "$APPLE_ID" \
    --team-id "$TEAM_ID" \
    --password "$APP_PASSWORD"

echo ""
echo -e "${GREEN}✓${NC} Credentials stored successfully!"
echo ""
echo -e "${YELLOW}Environment variables for build script:${NC}"
echo "export CODESIGN_IDENTITY=\"Developer ID Application: Gabriele Ottino (2K34CUCVB2)\""
echo "export APPLE_ID=\"$APPLE_ID\""
echo "export APPLE_TEAM_ID=\"$TEAM_ID\""
echo ""
echo -e "${YELLOW}Add these to your ~/.zshrc or run them before building:${NC}"
echo ""
echo "cat >> ~/.zshrc << 'EOF'"
echo "# rMirror notarization"
echo "export CODESIGN_IDENTITY=\"Developer ID Application: Gabriele Ottino (2K34CUCVB2)\""
echo "export APPLE_ID=\"$APPLE_ID\""
echo "export APPLE_TEAM_ID=\"$TEAM_ID\""
echo "EOF"
echo ""
echo -e "${GREEN}Setup complete!${NC} You can now run ./build_macos.sh"
echo ""
