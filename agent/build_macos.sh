#!/bin/bash
#
# Build macOS .dmg installer for rMirror Agent
#
# This script:
# 1. Converts PNG icon to .icns
# 2. Builds app with PyInstaller
# 3. Creates a .dmg installer
#

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
APP_NAME="rMirror"
VERSION="1.1.0"
BUNDLE_ID="io.rmirror.agent"

# Directories
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="$SCRIPT_DIR/build"
DIST_DIR="$SCRIPT_DIR/dist"
RESOURCES_DIR="$SCRIPT_DIR/resources"

echo -e "${GREEN}================================================${NC}"
echo -e "${GREEN}  Building rMirror macOS Installer${NC}"
echo -e "${GREEN}  Version: $VERSION${NC}"
echo -e "${GREEN}================================================${NC}"
echo ""

# Check prerequisites
echo -e "${YELLOW}→${NC} Checking prerequisites..."

if ! command -v python3 &> /dev/null; then
    echo -e "${RED}✗${NC} Python 3 is not installed"
    exit 1
fi

if ! command -v sips &> /dev/null; then
    echo -e "${RED}✗${NC} sips is not available (required for icon conversion)"
    exit 1
fi

if ! python3 -c "import PyInstaller" &> /dev/null; then
    echo -e "${YELLOW}  Installing PyInstaller...${NC}"
    pip3 install pyinstaller
fi

if ! command -v create-dmg &> /dev/null; then
    echo -e "${YELLOW}  Installing create-dmg...${NC}"
    brew install create-dmg 2>/dev/null || {
        echo -e "${RED}✗${NC} create-dmg is not installed and Homebrew is not available"
        echo -e "${YELLOW}  Please install Homebrew or create-dmg manually${NC}"
        exit 1
    }
fi

echo -e "${GREEN}✓${NC} All prerequisites met"
echo ""

# Step 1: Convert PNG icon to .icns
echo -e "${YELLOW}→${NC} Converting icon..."
mkdir -p "$BUILD_DIR/icon.iconset"

# Create iconset with all required sizes
for size in 16 32 128 256 512; do
    sips -z $size $size "$RESOURCES_DIR/icon.png" \
        --out "$BUILD_DIR/icon.iconset/icon_${size}x${size}.png" > /dev/null 2>&1
    
    # Create @2x versions
    size2x=$((size * 2))
    sips -z $size2x $size2x "$RESOURCES_DIR/icon.png" \
        --out "$BUILD_DIR/icon.iconset/icon_${size}x${size}@2x.png" > /dev/null 2>&1
done

# Convert iconset to .icns
iconutil -c icns "$BUILD_DIR/icon.iconset" -o "$BUILD_DIR/icon.icns"
rm -rf "$BUILD_DIR/icon.iconset"

echo -e "${GREEN}✓${NC} Icon converted to .icns"
echo ""

# Step 2: Build with PyInstaller
echo -e "${YELLOW}→${NC} Building app with PyInstaller..."
echo -e "   This may take a few minutes..."

# Clean previous builds
rm -rf "$DIST_DIR" "$SCRIPT_DIR/build/rMirror"

# Run PyInstaller via Poetry (ensures correct environment with all dependencies)
poetry run pyinstaller \
    --clean \
    --noconfirm \
    "$SCRIPT_DIR/rmirror.spec" 2>&1 | grep -v "^[0-9]* INFO:" || true

if [ ! -d "$DIST_DIR/rMirror.app" ]; then
    echo -e "${RED}✗${NC} PyInstaller failed to create app bundle"
    exit 1
fi

echo -e "${GREEN}✓${NC} App bundle created: $DIST_DIR/rMirror.app"
echo ""

# Step 3: Sign the app (optional, requires Apple Developer certificate)
echo -e "${YELLOW}→${NC} Code signing..."
if [ -n "$CODESIGN_IDENTITY" ]; then
    echo -e "   Signing with identity: $CODESIGN_IDENTITY"
    # Sign with hardened runtime enabled (required for notarization)
    codesign --force --deep --sign "$CODESIGN_IDENTITY" \
        --options runtime \
        --timestamp \
        "$DIST_DIR/rMirror.app"
    echo -e "${GREEN}✓${NC} App signed with hardened runtime"
else
    echo -e "${YELLOW}⚠${NC}  Skipping code signing (CODESIGN_IDENTITY not set)"
    echo -e "   The app will work but macOS will show a security warning"
fi
echo ""

# Step 4: Create DMG
echo -e "${YELLOW}→${NC} Creating DMG installer..."

DMG_NAME="rMirror-${VERSION}.dmg"
DMG_PATH="$DIST_DIR/$DMG_NAME"

# Remove old DMG if exists
rm -f "$DMG_PATH"

# Create DMG
create-dmg \
    --volname "rMirror Installer" \
    --volicon "$BUILD_DIR/icon.icns" \
    --window-pos 200 120 \
    --window-size 600 400 \
    --icon-size 100 \
    --icon "rMirror.app" 150 190 \
    --hide-extension "rMirror.app" \
    --app-drop-link 450 190 \
    --no-internet-enable \
    "$DMG_PATH" \
    "$DIST_DIR/rMirror.app" 2>&1 | grep -v "^hdiutil:" || true

if [ ! -f "$DMG_PATH" ]; then
    echo -e "${RED}✗${NC} Failed to create DMG"
    exit 1
fi

echo -e "${GREEN}✓${NC} DMG created: $DMG_PATH"
echo ""

# Step 5: Calculate size and checksum
DMG_SIZE=$(du -h "$DMG_PATH" | cut -f1)
DMG_SHA256=$(shasum -a 256 "$DMG_PATH" | cut -d' ' -f1)

# Print summary
echo -e "${GREEN}================================================${NC}"
echo -e "${GREEN}  Build Complete!${NC}"
echo -e "${GREEN}================================================${NC}"
echo ""
echo -e "App:      $DIST_DIR/rMirror.app"
echo -e "Installer: $DMG_PATH"
echo -e "Size:      $DMG_SIZE"
echo -e "SHA256:    $DMG_SHA256"
echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo -e "1. Test the installer: open $DMG_PATH"
echo -e "2. Upload to Backblaze: b2 upload-file rmirror-downloads $DMG_PATH releases/v${VERSION}/$DMG_NAME"
echo -e "3. Update download link: https://downloads.rmirror.io/releases/v${VERSION}/$DMG_NAME"
echo ""
