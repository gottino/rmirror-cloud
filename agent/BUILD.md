# Building the rMirror macOS Installer

`build_macos.sh` builds `dist/rMirror.app` and `dist/rMirror-<version>.dmg`. The
version comes from `app/__version__.py` (also read by `rmirror.spec`); keep
`version` in `pyproject.toml` the same, because `release.sh` reads it from there.

## Prerequisites

- macOS 12 or later, Xcode Command Line Tools, Python 3.11+, Poetry
- `create-dmg` (`brew install create-dmg`; the script tries to install it)
- For a release build:
  - a **Developer ID Application** certificate in your keychain
  - notarization credentials stored once as the keychain profile `rmirror-notarization`:

    ```bash
    xcrun notarytool store-credentials "rmirror-notarization" \
        --apple-id "<apple id>" --team-id "<team id>" --password "<app-specific password>"
    ```

## Release build (signed and notarized)

```bash
cd agent
poetry install
CODESIGN_IDENTITY="Developer ID Application: <name> (<team id>)" ./build_macos.sh
```

Signing is required: without `CODESIGN_IDENTITY` the script stops with an error.
Every signing, notarization or stapling failure exits non-zero. The steps are:

1. Convert `resources/icon.png` to `.icns` and build the app with PyInstaller (`rmirror.spec`).
2. Strip old signatures from bundled `.so`/`.dylib` files, then sign the app with
   hardened runtime and a timestamp.
3. Create and sign the DMG.
4. Notarize the DMG (`notarytool submit --keychain-profile rmirror-notarization --wait`)
   and staple the ticket.
5. Verify strictly: `codesign --verify --deep --strict` on the app, `codesign --verify`
   on the DMG, `stapler validate`, and `spctl --assess --type open` on the DMG.

The script prints the DMG's size and SHA-256 at the end. Upload it with `release.sh`.

## Local test build (unsigned)

```bash
./build_macos.sh --unsigned
```

Skips signing, notarization and verification and leaves a `dist/.unsigned` marker;
`release.sh` refuses to upload such a build. macOS warns when opening it (for local
testing, remove the quarantine flag with `xattr -cr dist/rMirror.app`).

## Testing the build

```bash
open dist/rMirror-<version>.dmg   # drag rMirror.app to Applications, then launch it
```

The menu-bar icon should appear and the web UI should open at http://localhost:5555.

## Version bump

Change `__version__` in `app/__version__.py` and `version` in `pyproject.toml`, then rebuild.

## CI

`.github/workflows/build-agent.yml` and `build-agent-intel.yml` build the agent in GitHub Actions.
