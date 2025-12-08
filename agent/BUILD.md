# Building rMirror macOS Installer

This document describes how to build the macOS `.dmg` installer for the rMirror Agent.

## Prerequisites

### Required
- macOS 12 (Monterey) or later
- Python 3.11 or later
- Xcode Command Line Tools (`xcode-select --install`)

### Optional (for code signing)
- Apple Developer Account
- Developer ID Application certificate

## Quick Start

```bash
# 1. Install dependencies
cd agent
poetry install

# 2. Install build tools
brew install create-dmg

# 3. Build the installer
./build_macos.sh
```

The resulting `.dmg` will be in `agent/dist/rMirror-1.0.0.dmg`

## Build Steps (Manual)

If you want to understand what the build script does:

### 1. Install PyInstaller
```bash
poetry add --group dev pyinstaller
```

### 2. Convert Icon
```bash
# Create iconset
mkdir -p build/icon.iconset
for size in 16 32 128 256 512; do
    sips -z $size $size resources/icon.png \
        --out "build/icon.iconset/icon_${size}x${size}.png"
done

# Convert to .icns
iconutil -c icns build/icon.iconset -o build/icon.icns
```

### 3. Build with PyInstaller
```bash
pyinstaller --clean --noconfirm rmirror.spec
```

### 4. Create DMG
```bash
create-dmg \
    --volname "rMirror Installer" \
    --volicon "build/icon.icns" \
    --window-pos 200 120 \
    --window-size 600 400 \
    --icon-size 100 \
    --icon "rMirror.app" 150 190 \
    --app-drop-link 450 190 \
    "dist/rMirror-1.0.0.dmg" \
    "dist/rMirror.app"
```

## Code Signing (Optional but Recommended)

To sign the app with your Apple Developer certificate:

```bash
# Set your Developer ID
export CODESIGN_IDENTITY="Developer ID Application: Your Name (TEAM_ID)"

# Run build (will automatically sign)
./build_macos.sh
```

To notarize the app for distribution (requires Apple Developer account):

```bash
# Submit for notarization
xcrun notarytool submit dist/rMirror-1.0.0.dmg \
    --apple-id "your@email.com" \
    --password "@keychain:AC_PASSWORD" \
    --team-id "TEAM_ID" \
    --wait

# Staple the notarization ticket
xcrun stapler staple dist/rMirror-1.0.0.dmg
```

## Testing

### Test the DMG
```bash
# Mount the DMG
open dist/rMirror-1.0.0.dmg

# Drag rMirror.app to Applications
# Launch from Applications folder
```

### Test the App
```bash
# Direct launch
open dist/rMirror.app

# Check if it runs
# You should see the menubar icon appear
# Open http://localhost:5555 in your browser
```

## Troubleshooting

### "App is damaged and can't be opened"
This happens with unsigned apps. Solutions:
1. Sign the app (recommended)
2. Remove quarantine: `xattr -cr dist/rMirror.app`

### "PyInstaller: command not found"
Install it: `poetry add --group dev pyinstaller`

### "create-dmg: command not found"
Install it: `brew install create-dmg`

### Icon doesn't appear
Make sure `resources/icon.png` exists and is at least 512x512 pixels.

### Web UI doesn't work
Check that Flask templates are included in the spec file:
```python
datas=[('app/web/templates', 'app/web/templates')]
```

## Distribution

### Upload to Backblaze B2
```bash
# Authorize
b2 authorize-account <key_id> <application_key>

# Upload
b2 upload-file rmirror-downloads \
    dist/rMirror-1.0.0.dmg \
    releases/v1.0.0/rMirror-1.0.0.dmg

# Make public
b2 update-bucket --bucketType allPublic rmirror-downloads
```

### Update Download Link
After uploading, users can download from:
```
https://downloads.rmirror.io/releases/v1.0.0/rMirror-1.0.0.dmg
```

## CI/CD (GitHub Actions)

See `.github/workflows/build-macos-agent.yml` for automated builds on release tags.

## App Bundle Structure

The final app bundle structure:
```
rMirror.app/
├── Contents/
│   ├── Info.plist          # App metadata
│   ├── MacOS/
│   │   └── rMirror         # Executable
│   ├── Resources/
│   │   ├── icon.icns       # App icon
│   │   ├── app/            # Python code
│   │   │   └── web/
│   │   │       └── templates/  # Flask templates
│   │   └── resources/      # Icons, assets
│   └── Frameworks/         # Python runtime, dependencies
```

## Version Bumping

To release a new version:

1. Update version in `pyproject.toml`
2. Update version in `build_macos.sh`
3. Update version in `rmirror.spec`
4. Rebuild: `./build_macos.sh`

## Resources

- [PyInstaller Documentation](https://pyinstaller.org/)
- [create-dmg GitHub](https://github.com/create-dmg/create-dmg)
- [Apple Code Signing Guide](https://developer.apple.com/support/code-signing/)
- [Apple Notarization Guide](https://developer.apple.com/documentation/security/notarizing_macos_software_before_distribution)
