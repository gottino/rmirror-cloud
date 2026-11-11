# /release-agent

Build, sign, notarize, and release a new version of the rMirror macOS agent.

## Usage

```
/release-agent [version]
```

## Arguments

- `version` (optional): New version number (e.g., `1.6.1`). If not provided, uses the current version from `agent/app/__version__.py`.

## Instructions

Execute the following steps in order from the repository root. Stop and report if any step fails.

### Step 1: Version Check/Bump

The version lives in two places that must match: `agent/pyproject.toml` (`version = "..."`) and `agent/app/__version__.py` (`__version__ = "..."`). `build_macos.sh` and the CI builds read `__version__.py`; `release.sh` reads `pyproject.toml`.

1. Read the current version from both files
2. If a new version was provided as argument, update it in both files
3. Report the version being released

### Step 2: Build, sign, notarize

`build_macos.sh` does everything in one run: icon conversion, PyInstaller build, code signing of the app, DMG creation (`create-dmg`), DMG signing, notarization (keychain profile `rmirror-notarization`) and stapling. It exits if `CODESIGN_IDENTITY` is not set.

```bash
cd agent
export CODESIGN_IDENTITY="Developer ID Application: <your name> (<team id>)"
./build_macos.sh
```

Verify that `dist/rMirror-<version>.dmg` exists and that the script reported "Notarized and stapled".

### Step 3: Release

`release.sh` uploads the DMG to Backblaze B2 (`releases/v<version>/`), uploads `releases/latest/version.json` (used by the agent's update check), sets `agent_latest_version` in `backend/app/config.py`, and offers to commit and push that change (a push to `main` deploys staging).

```bash
cd agent
./release.sh
```

B2 credentials are read from the macOS Keychain (`./b2-keychain.sh store` once, `./b2-keychain.sh get`).

### Step 4: Report Summary

Report to the user:
- Version released
- DMG path and size
- SHA256 checksum: `shasum -a 256 dist/rMirror-${VERSION}.dmg`
- Download URL: `https://f000.backblazeb2.com/file/rmirror-downloads/releases/v${VERSION}/rMirror-${VERSION}.dmg`
- Whether the backend config change was committed/pushed (production picks up the new `agent_latest_version` only after the manual "Deploy to Production" workflow)

## Prerequisites

- Developer ID certificate installed: `security find-identity -v -p codesigning`
- Notarization credentials stored: keychain profile "rmirror-notarization"
- B2 credentials in Keychain: `./b2-keychain.sh store`
- `b2` CLI installed: `brew install b2-tools`
- Poetry and dependencies installed
- create-dmg installed: `brew install create-dmg`

The Intel build is produced by the "Build Agent (Intel)" GitHub workflow (`build-agent-intel.yml`); the Apple Silicon one by `build-agent.yml`.

## Examples

```
/release-agent           # Release with current version
/release-agent 1.6.1     # Bump to 1.6.1 and release
```
