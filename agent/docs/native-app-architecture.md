# rMirror for Mac 2.0: architecture record

Date: 2026-11-23. Companion to `local-api.md` (the contract between the two processes).

## Shape

```
rMirror.app  (Swift, universal)                      agent/macos/
├─ AppKit lifecycle: NSApplicationDelegate, NSStatusItem, NSWindow
├─ SwiftUI views hosted in those windows
├─ CoreSupervisor: starts, watches, restarts and stops the core
├─ LocalAPI client (loopback HTTP, per-launch token)
├─ Sparkle 2 (optional at build time)
└─ Contents/Resources/core/rmirror-core   (Python, PyInstaller onedir, per architecture)   agent/app/
      Flask on 127.0.0.1:5555 · sync loop · watcher · upload manifest · keychain token
```

## Decisions

| # | Decision | Why |
|---|---|---|
| 1 | Swift shell + Python core as a child process, not a rewrite | The pain is in the shell; the sync logic is sound and covered by tests. |
| 2 | Core lives in `Contents/Resources/core/`, started with `Process` as a plain child | Tested 2026-11-22: Full Disk Access granted to the app covers the child (direct launch, rebuild, login item, macOS 27.0.1 and 27.2.1). `Contents/Frameworks` fails signing because the payload has non-code files. |
| 3 | AppKit lifecycle hosting SwiftUI; no `MenuBarExtra`, no SwiftUI `Settings` scene | Those are the unreliable parts for menu-bar apps. |
| 4 | Dock icon while a window is open (`.regular`), menu-bar-only otherwise (`.accessory`) | UX review: "find the agent window" is high friction. |
| 5 | Swift package (`swift build`/`swift test`) plus a bundle script; no Xcode project in the repo | Reviewable diffs, runs in CI, no project file for agents to corrupt. Fallback: XcodeGen. |
| 6 | Swift 5 language mode, macOS 13 minimum | Avoids Swift 6 strict-concurrency churn; macOS 13 is needed for `SMAppService`. |
| 7 | A new `/api/v2` surface for the app; legacy routes untouched | Clean contract of codes and numbers; legacy menu-bar mode keeps working until it is removed. |
| 8 | Per-launch app token on `/api/v2` | Other local processes and web pages cannot drive the core. |
| 9 | Core exits when stdin closes | No orphan holding port 5555 if the app crashes or is force-killed. |
| 10 | Sign-in flow, keychain item, config path, manifest and bundle id unchanged | Hardened in the security audit; existing users keep their state. |
| 11 | All user-facing wording lives in Swift (`Copy`), core returns codes | Issue #47: no tokens, rate limits, callbacks or logs in front of users. |
| 12 | Sparkle is a build-time option; without a public key the app uses the `version.json` check | Key and feed are the owner's to create at release time. |
| 13 | Legacy menu-bar mode (`rumps`, Flask page) stays buildable and frozen in 2.0 | Removed in a follow-up after hand-testing. |

## Swift package layout (`agent/macos/`)

```
Package.swift
Sources/RMirrorKit/        library, no UI, unit-tested
  API/                     LocalAPIClient, request/response models, errors
  Core/                    CoreSupervisor, CoreLocator, launch token
  Model/                   AppStore (ObservableObject), Stage (which screen), NotebookList (search, grouping, selection maths)
  Copy/                    every user-facing string, as functions of codes and counts
Sources/RMirrorApp/        executable
  App/                     main, AppDelegate, StatusItemController, WindowCoordinator, LoginItem, Updater
  Onboarding/              sign-in, missing reMarkable app, permission, first sync, progress
  Main/                    main window: status, allowance, notebook list, save-and-sync footer
  Settings/                settings window, developer options
  Theme/                   colours, type, shared controls
Tests/RMirrorKitTests/
Resources/                 Info.plist template (no entitlements needed; icon generated at build time)
scripts/                   build_app.sh (build, assemble, sign, notarize), smoke_core.sh (see macos/README.md)
```

## Onboarding stage logic (single source of truth, in `RMirrorKit/Model`)

Derived from the supervisor status and `GET /api/v2/state` in `Stage.derive`, first match wins:

1. core failed → `coreProblem(failure)` (port in use, cannot launch, never ready, crash loop)
2. core not running, or no state yet → `starting`
3. `auth.sign_in_required` → `signIn(.expired)`
4. `auth.state == checking` → `starting` ("Checking your sign-in…"); `offline` carries on as signed in
5. not signed in → `signIn(.signedOut)`
6. `folder.state == missing` → `remarkableMissing`; `unreadable` → `permission`
7. guided first sync started in this session: running → `firstSyncProgress`, done → `firstSyncResult` (until dismissed)
8. `first_sync.completed == false` → `firstSync` (or `firstSyncProgress` if a sync is already running)
9. otherwise → `ready` (main window)

## Supervisor rules

- Launch with a fresh 32-byte token in `RMIRROR_APP_TOKEN`; keep the stdin pipe open.
- Ready only when the `RMIRROR_CORE_READY` line arrives on the child's stdout; time out at 30 s. A reply on the port is never used as readiness, so the launch token cannot be sent to a different process listening there.
- Unexpected exit: restart with backoff 1, 2, 5, 15, 30 s; after 5 failures in 2 minutes stop and show `coreFailed`.
- Exit code 3 → `portInUse`, no restart loop.
- Quit: `SIGTERM`, wait up to 8 s, then `SIGKILL`.
- After the user grants Full Disk Access the child must be restarted; macOS normally also asks the user to quit
  and reopen the app. The permission screen offers "Reopen rMirror".

## Not decided here

- Sparkle feed layout for two architectures (one feed per architecture vs one feed with two enclosures).
- Removal of the legacy mode.
