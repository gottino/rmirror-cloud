# /release-agent

Build, sign, notarize, and release a new version of the rMirror macOS agent.

## Usage

```
/release-agent [version]
```

## Arguments

- `version` (optional): New version number (e.g., `1.4.2`). If not provided, uses current version from pyproject.toml.

## Instructions

Execute the following steps in order. Stop and report if any step fails.

### Step 1: Version Check/Bump

1. Read current version from `agent/pyproject.toml`
2. If a new version was provided as argument:
   - Update version in `agent/pyproject.toml`
   - Update VERSION in `agent/build_macos.sh`
3. Report the version being released

### Step 2: Build with PyInstaller

```bash
cd /Users/gottino/Documents/Development/rmirror-cloud/agent
rm -rf dist build/rMirror
poetry install --with dev
poetry run pyinstaller --clean --noconfirm rmirror.spec
```

Verify `dist/rMirror.app` exists.

### Step 3: Clean Extended Attributes

PyInstaller may copy files with extended attributes that break code signing.

```bash
cd /Users/gottino/Documents/Development/rmirror-cloud/agent
codesign --remove-signature dist/rMirror.app 2>/dev/null || true
xattr -cr dist/rMirror.app
```

### Step 4: Code Sign the App Bundle

```bash
cd /Users/gottino/Documents/Development/rmirror-cloud/agent
codesign --force --deep --sign "Developer ID Application: Gabriele Ottino (2K34CUCVB2)" \
    --options runtime --timestamp dist/rMirror.app
```

Verify with:
```bash
codesign --verify --deep --strict dist/rMirror.app
```

### Step 5: Create DMG

```bash
cd /Users/gottino/Documents/Development/rmirror-cloud/agent
VERSION=$(grep '^version = ' pyproject.toml | sed 's/version = "\(.*\)"/\1/')
rm -f "dist/rMirror-${VERSION}.dmg"
create-dmg \
    --volname "rMirror Installer" \
    --volicon "build/icon.icns" \
    --window-pos 200 120 \
    --window-size 600 400 \
    --icon-size 100 \
    --icon "rMirror.app" 150 190 \
    --hide-extension "rMirror.app" \
    --app-drop-link 450 190 \
    --no-internet-enable \
    "dist/rMirror-${VERSION}.dmg" \
    "dist/rMirror.app"
```

If icon.icns doesn't exist, create it first:
```bash
mkdir -p build/icon.iconset
for size in 16 32 128 256 512; do
    sips -z $size $size resources/icon.png --out "build/icon.iconset/icon_${size}x${size}.png"
    sips -z $((size*2)) $((size*2)) resources/icon.png --out "build/icon.iconset/icon_${size}x${size}@2x.png"
done
iconutil -c icns build/icon.iconset -o build/icon.icns
rm -rf build/icon.iconset
```

### Step 6: Sign the DMG

```bash
cd /Users/gottino/Documents/Development/rmirror-cloud/agent
VERSION=$(grep '^version = ' pyproject.toml | sed 's/version = "\(.*\)"/\1/')
codesign --sign "Developer ID Application: Gabriele Ottino (2K34CUCVB2)" "dist/rMirror-${VERSION}.dmg"
```

### Step 7: Notarize with Apple

```bash
cd /Users/gottino/Documents/Development/rmirror-cloud/agent
VERSION=$(grep '^version = ' pyproject.toml | sed 's/version = "\(.*\)"/\1/')
xcrun notarytool submit "dist/rMirror-${VERSION}.dmg" \
    --keychain-profile "rmirror-notarization" \
    --wait
```

This may take several minutes. Wait for "status: Accepted".

### Step 8: Staple Notarization Ticket

```bash
cd /Users/gottino/Documents/Development/rmirror-cloud/agent
VERSION=$(grep '^version = ' pyproject.toml | sed 's/version = "\(.*\)"/\1/')
xcrun stapler staple "dist/rMirror-${VERSION}.dmg"
```

Verify with:
```bash
xcrun stapler validate "dist/rMirror-${VERSION}.dmg"
```

### Step 9: Upload to Backblaze B2

Load credentials from Keychain and upload:

```bash
cd /Users/gottino/Documents/Development/rmirror-cloud/agent
eval $(./b2-keychain.sh get)
b2 account authorize 2>/dev/null || b2 account authorize
VERSION=$(grep '^version = ' pyproject.toml | sed 's/version = "\(.*\)"/\1/')
b2 file upload rmirror-downloads "dist/rMirror-${VERSION}.dmg" "releases/v${VERSION}/rMirror-${VERSION}.dmg"
```

### Step 10: Update Dashboard Download Link

Edit `/Users/gottino/Documents/Development/rmirror-cloud/dashboard/app/dashboard/page.tsx`:

Find the line with `backblazeb2.com/file/rmirror-downloads/releases/` and update the version number to match the new release.

### Step 11: Commit and Push (Ask User First)

Ask the user if they want to commit and push the changes:
- `agent/pyproject.toml` (if version was bumped)
- `agent/build_macos.sh` (if version was bumped)
- `dashboard/app/dashboard/page.tsx`

If yes:
```bash
cd /Users/gottino/Documents/Development/rmirror-cloud
git add agent/pyproject.toml agent/build_macos.sh dashboard/app/dashboard/page.tsx
git commit -m "chore: release agent v${VERSION}

- Built, signed, and notarized macOS installer
- Updated dashboard download link

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
git push
```

### Step 12: Report Summary

Report to the user:
- Version released
- DMG path and size
- SHA256 checksum: `shasum -a 256 dist/rMirror-${VERSION}.dmg`
- Download URL: `https://f000.backblazeb2.com/file/rmirror-downloads/releases/v${VERSION}/rMirror-${VERSION}.dmg`
- Whether changes were committed/pushed

## Prerequisites

- Developer ID certificate installed: `security find-identity -v -p codesigning`
- Notarization credentials stored: keychain profile "rmirror-notarization"
- B2 credentials in Keychain: `./b2-keychain.sh store`
- Poetry and dependencies installed
- create-dmg installed: `brew install create-dmg`

## Examples

```
/release-agent           # Release with current version
/release-agent 1.4.2     # Bump to 1.4.2 and release
```
