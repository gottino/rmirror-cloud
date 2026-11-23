# rMirror for Mac 2.0 (Swift app)

The native shell of the Mac app: AppKit + SwiftUI, Swift package, no Xcode project. It starts the Python sync
core (`agent/app`, built as `rmirror-core`) as a child process and talks to it over the local API v2.
Design: [`../docs/native-app-architecture.md`](../docs/native-app-architecture.md); contract between the two
processes: [`../docs/local-api.md`](../docs/local-api.md); updates: [`docs/sparkle.md`](docs/sparkle.md).

## Develop

```sh
cd agent/macos
swift build          # debug build: .build/debug/RMirrorApp
swift test           # RMirrorKit unit tests (live-core tests are skipped, see below)
```

Outside a `.app` bundle the app finds no bundled core, so point it at the core from source
(`CoreLocator` in `Sources/RMirrorKit/Core/CoreSupervisor.swift`). This override works in **debug builds only**
(`swift build`); a release build ignores these variables and only ever starts the bundled
`Contents/Resources/core/rmirror-core`:

```sh
cd agent && poetry install --no-root && cd macos
RMIRROR_CORE_CMD="$(cd .. && poetry env info -e)" \
RMIRROR_CORE_ARGS="-m app.main --headless" \
RMIRROR_CORE_CWD="$(cd .. && pwd)" \
.build/debug/RMirrorApp
```

- `RMIRROR_CORE_CMD`: executable to start; `RMIRROR_CORE_ARGS`: its arguments, split on spaces (default
  `--headless`); `RMIRROR_CORE_CWD`: its working directory. The app sends the launch token itself, as the first line on the core's stdin.
- The core does not inherit the app's environment. It gets `HOME`, `PATH`, `TMPDIR`, `USER`, `LOGNAME`, `LANG`,
  `LC_ALL`, `LC_CTYPE`, `SHELL`, `__CF_USER_TEXT_ENCODING` (when set), the token and `PYTHONUNBUFFERED=1`; debug
  builds also pass `RMIRROR_CONFIG_PATH` and `PYTHON_KEYRING_BACKEND` through, so a throwaway config works there.
- The core from source uses your real `~/.config/rmirror` and login keychain, like the installed app.
- Outside a bundle Sparkle is never started and "Reopen rMirror" is not offered.

Screens without a core: `.build/debug/RMirrorApp --render-screens <dir>` writes a PNG of every screen, light and
dark, from fixture data and exits.

Live-core tests (`Tests/RMirrorKitTests/Live/`): start a core with a throwaway `HOME` and config (they expect a
signed-out core), e.g. `(printf '%s\n' "$TOKEN"; sleep 600) | HOME=$TMP RMIRROR_CONFIG_PATH=$TMP/config.yaml
PYTHON_KEYRING_BACKEND=keyring.backends.null.Keyring rmirror-core --headless` (the launch token is the first line on
the core's stdin, and the core stops when that pipe closes), then run
`RMIRROR_LIVE_PORT=<port> RMIRROR_LIVE_TOKEN=$TOKEN swift test`.

## Package: `scripts/build_app.sh`

```sh
cd agent/macos
CODESIGN_IDENTITY="Developer ID Application: <Name> (<TEAMID>)" ./scripts/build_app.sh
```

Produces `build/app/rMirror.app` and `build/dist/rMirror-<version>-<arch>.dmg`: Developer ID signed, hardened
runtime, notarized, DMG stapled. `--help` lists everything; the main switches:

| | |
|---|---|
| `--unsigned` | ad-hoc signature, no notarization, no Gatekeeper checks. Local testing only. |
| `--skip-notarize` | Developer ID signed but not notarized. |
| `--arch arm64\|x86_64` | architecture of the Python core (default: host). PyInstaller builds for the Python it runs on, so build each core natively (CI: the Intel runner for x86_64). The Swift executable is always universal. |
| `NOTARY_PROFILE` | `notarytool` keychain profile, default `rmirror-notarization` (`xcrun notarytool store-credentials`). `NOTARY_KEYCHAIN` selects a non-default keychain (CI). |
| `BUILD_DIR` | default `agent/macos/build/` (gitignored). The script refuses iCloud / File Provider locations: they add `com.apple.FinderInfo` xattrs that break `codesign --verify --strict`. |
| `BUILD_NUMBER` | `CFBundleVersion`; default the git commit count. |
| `SPARKLE_FEED_URL` + `SPARKLE_PUBLIC_ED_KEY` | both set: `SUFeedURL`, `SUPublicEDKey`, `SUEnableAutomaticChecks` go into Info.plist. Otherwise absent and Sparkle stays off. |
| `DMG_FINDER_LAYOUT=1` | let `create-dmg` arrange the DMG window via Finder AppleScript (needs Automation permission). Default skips it: the DMG has the app and an Applications link, without icon positions. |

Steps, in order (each failure names its step and exits non-zero):

1. Preflight: tools, signing identity, version from `agent/app/__version__.py`, build dir not in iCloud.
2. Core: `poetry run pyinstaller --clean rmirror-core.spec` into `build/pyinstaller/`.
3. Swift: `swift build -c release --arch arm64 --arch x86_64` (scratch path `build/swift/`); if the universal
   build fails it falls back to the host architecture and warns loudly.
4. Assemble `rMirror.app`: `Contents/MacOS/RMirrorApp`, `Contents/Resources/core/` (whole onedir tree; not
   `Contents/Frameworks`, which fails signing because of the non-code files), `Contents/Frameworks/Sparkle.framework`
   (`ditto`, symlinks kept), Info.plist from `Resources/Info.plist`, `AppIcon.icns` made from
   `agent/resources/icon.png`, rpath `@executable_path/../Frameworks`.
5. `xattr -cr` on the fresh bundle. `com.apple.provenance` cannot be removed and is ignored by codesign; anything
   else left fails the build.
6. Sign inside-out with `--options runtime --timestamp`, never `--deep`: every Mach-O in the core (found with
   `file`), the core executable, Sparkle's XPC services, `Autoupdate`, `Updater.app`, the framework, the app.
7. `codesign --verify --deep --strict`, then `scripts/smoke_core.sh` runs the **signed** core from the bundle
   (throwaway HOME, port 5599, null keyring, unreachable cloud): ready line, `/health` 200, `/api/v2/state` 401
   without and 200 with the app token, exit 0 on stdin EOF.
8. DMG (`create-dmg`, APFS, LZFSE `ULFO`, Applications link), signed with the Developer ID.
9. `xcrun notarytool submit --wait` (retries transient errors up to 4 times, stops on credential/agreement
   errors, prints `notarytool log` for a rejected submission), `xcrun stapler staple` on the DMG.
10. Final checks: `codesign --verify --deep --strict` (app), `stapler validate` (DMG),
    `spctl -a -t open --context context:primary-signature` (DMG), `spctl -a` on the app copied out of the mounted
    DMG; prints size and sha256.

### Notarization and stapling

The DMG is the one thing submitted. Apple's guidance is to notarize and staple the outermost container you ship:
notarizing the DMG records tickets for everything inside it, and the DMG gets the stapled ticket. The app inside is
not stapled itself; when it is opened after being copied out, Gatekeeper fetches its ticket online
(`spctl` reports `source=Notarized Developer ID`). Stapling the app too would need a second submission of the app
alone before the DMG is made.

### Entitlements

None, for the app and for the core. Tested 2026-11-23 on arm64 (macOS 27.2): the core signed with hardened runtime
and no entitlements passes `smoke_core.sh`. The legacy Intel build needed
`allow-unsigned-executable-memory` and `disable-library-validation` for libffi closures created by PyObjC; the
headless core does not bundle PyObjC (`rmirror-core.spec` excludes `rumps`, `objc`, `AppKit`, `Foundation`).
x86_64 is **untested**: if the Intel core fails under the hardened runtime, add the single narrowest entitlement in
`Resources/core.entitlements` (the script applies it to the core executable only) and record the error here.
`Resources/app.entitlements`, if ever added, is applied to the app.

### CI

- `.github/workflows/build-mac-app.yml` (macos-15, arm64 core) and `build-mac-app-intel.yml` (macos-15-intel,
  x86_64 core): `workflow_dispatch` only, same secrets as the legacy agent workflows, DMG kept as a workflow
  artifact. No upload, no release.
- `ci.yml` job `agent-macos-checks`: `swift build` + `swift test` on pull requests that change `agent/macos/` (or `ci.yml` itself). A cheap Linux job, `agent-macos-changes`, decides that first, so other pull requests skip the Swift job without ever waiting for a macOS runner.

## Not done by the script (release time, by the owner)

- Sparkle: create the EdDSA key once, build with `SPARKLE_FEED_URL` / `SPARKLE_PUBLIC_ED_KEY`, run
  `generate_appcast`, publish one appcast per architecture ([`docs/sparkle.md`](docs/sparkle.md) sections 4-5).
- Upload the DMGs (B2 `releases/v<version>/`) and the appcasts; update `version.json`.
- Announce the version: `agent_latest_version` in `backend/app/config.py` and `backend/.env.example` (the backend
  test compares them), then deploy. Until then existing users are not offered 2.0.
- Version source: `agent/app/__version__.py` and `agent/pyproject.toml` (both 2.0.0). Note that the legacy
  `agent/build_macos.sh` reads the same file, so a legacy build from this branch is also labelled 2.0.0.
