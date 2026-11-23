# Building the rMirror macOS app

## rMirror for Mac 2.0 (Swift app + Python core)

The 2.0 app lives in `agent/macos/` and is built by one script. Full instructions (options, signing, notarization,
Sparkle, CI): [`macos/README.md`](macos/README.md). Design: [`docs/native-app-architecture.md`](docs/native-app-architecture.md).

```bash
cd agent/macos
CODESIGN_IDENTITY="Developer ID Application: <name> (<team id>)" ./scripts/build_app.sh
```

This builds the core with PyInstaller (`rmirror-core.spec`), the Swift app (universal), assembles `rMirror.app`, signs,
notarizes and staples a DMG. Output: `build/app/rMirror.app` and `build/dist/rMirror-<version>-<arch>.dmg`. Use
`--unsigned` for a local test build. Run it outside iCloud: the script refuses iCloud locations, and the main checkout
under `~/Documents` is in iCloud, so use a worktree elsewhere or set `BUILD_DIR`.

Status: nothing built by this script has been released. The two CI workflows (`build-mac-app.yml`,
`build-mac-app-intel.yml`) are manual and have not been run yet; the Intel build has never been run. Sparkle has no key
or feed yet.

---

## Legacy 1.x build (frozen)

Everything below describes the legacy PyInstaller menu-bar app (rumps + Flask page in the browser), which still builds
but is frozen and will be removed in a follow-up. Note that `build_macos.sh` reads the same `app/__version__.py`, so a
legacy build from this branch is labelled 2.0.0.

### Building the legacy installer

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
