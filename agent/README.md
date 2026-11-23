# rMirror for Mac

Syncs your reMarkable notebooks to rMirror Cloud. Version 2.0 is a native Mac app (Swift) that runs the existing
Python sync code as a hidden helper process ("the core").

Status: 2.0 is on the branch `claude/agent-native-app` in draft PRs and has not been released. The released app is
1.7.0 (the legacy mode, below). Sparkle updates have no key or feed yet and the Intel build has never been run.

## What rMirror for Mac 2.0 does

- Opens a normal window. First run is a guided flow:
  1. Sign in (opens your browser, then returns to the app).
  2. If the reMarkable desktop app's folder is missing, it says so and waits for the app.
  3. If macOS blocks access to that folder, a permission step walks through turning on Full Disk Access for rMirror
     in System Settings, with a "Reopen rMirror" button.
  4. A guided first sync: rMirror suggests recent notebooks, you can choose others, then it uploads them.
- After that it lives in the menu bar. The menu bar item shows the sync status and offers "Open rMirror",
  "Settings...", "Check for Updates..." and "Quit rMirror". The Dock icon shows only while a window is open.
- The main window lists your notebooks with a sync indicator, lets you tick which ones stay in sync and search them, shows this month's page allowance, and has an "Open on the web" link.
- Settings: open rMirror at login, account (sign out), limit pages per notebook, the reMarkable folder, and
  "Developer options" for self-hosters (server: rMirror Cloud, Staging or a custom API URL; changing it needs a new
  sign-in).
- Needs macOS 13 or later.

All wording the user sees comes from the Swift app. The core only returns codes and numbers.

## How it fits together

```
rMirror.app (Swift)                       agent/macos/
  windows, menu bar item, updates
  └─ Contents/Resources/core/rmirror-core  (Python, started as a child process)    agent/app/
       file watcher, sync queue, upload to the cloud, local API on 127.0.0.1:5555
```

The app starts the core with a per-launch token, polls the core's local API (`/api/v2`), and treats the core as ready
only when it prints its ready line. If the app quits or crashes, the core exits when its stdin closes. The sign-in
token is stored in the macOS Keychain; settings and logs stay in `~/.config/rmirror/`.

Details: [`docs/native-app-architecture.md`](docs/native-app-architecture.md) (decisions),
[`docs/local-api.md`](docs/local-api.md) (contract between the two processes),
[`macos/README.md`](macos/README.md) (develop, run, package), [`macos/docs/sparkle.md`](macos/docs/sparkle.md) (updates).

## Develop

Swift app (from `agent/macos`):

```bash
swift build
swift test
```

To run the app against the core from source, set `RMIRROR_CORE_CMD`, `RMIRROR_CORE_ARGS` and `RMIRROR_CORE_CWD` as
described in [`macos/README.md`](macos/README.md). `.build/debug/RMirrorApp --render-screens <dir>` writes a PNG of
every screen from fixture data.

Core (from `agent`):

```bash
poetry install
poetry run pytest
RMIRROR_APP_TOKEN=<64 hex chars> poetry run python -m app.main --headless
```

Package (signed, notarized DMG; run outside iCloud): `macos/scripts/build_app.sh`, see [`BUILD.md`](BUILD.md).

## Configuration

The core reads `~/.config/rmirror/config.yaml` (also `~/.rmirror/config.yaml`, `./config.yaml`; override with
`--config` or `RMIRROR_CONFIG_PATH`). Most people never edit it: the app changes the folder, page limit and server.
`config.example.yaml` lists the keys. There are no credentials in the file; the sign-in is kept in the Keychain. Password
sign-in no longer exists.

Logs: `~/.config/rmirror/agent.log`.

## Legacy 1.x mode (frozen)

The 1.x app is a menu-bar program (rumps) with a Flask page at `http://localhost:5555` that you open in a browser.
It still builds (`build_macos.sh`, `rmirror.spec`) and runs (`poetry run python -m app.main`, add `--foreground
--debug` for a terminal), but it is frozen: no new features, and it will be removed in a follow-up after 2.0 is
hand-tested. Its menu has Status, Open Web UI, Check for Updates, Settings and Quit. `install.sh`, `uninstall.sh`,
`launch-rmirror.sh` and `launch-rmirror.bat` belong to this mode; they are not part of 2.0 and have not been
re-checked for it. The docs `STANDALONE_APP.md`, `INITIAL_SYNC_FEATURE.md` and `test_initial_sync_manual.md` describe
the legacy UI.

## License

AGPL-3.0 - See LICENSE file

## Support

- Issues: https://github.com/gottino/rmirror-cloud/issues
- Discussions: https://github.com/gottino/rmirror-cloud/discussions
