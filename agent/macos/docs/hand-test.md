# Hand-test for rMirror for Mac 2.0

What could not be checked without a person at the Mac. Use staging (`https://staging.rmirror.io`) and a test
account. Budget about 30 minutes. Note the macOS version and whether the Mac is Apple Silicon or Intel.

Before you start: quit any running rMirror 1.x from its menu bar icon (both use port 5555).

## 1. Install and first open

1. Open `rMirror-2.0.0-arm64.dmg`, drag rMirror to Applications (replace the 1.x app if asked), open it.
2. Expected: Gatekeeper shows the normal "downloaded from the internet" dialog once, not a warning that the app
   cannot be checked. A menu bar icon appears and the rMirror window opens by itself, with a Dock icon.
3. Record every macOS prompt that appears (issue #48 asks for this list).

## 2. Existing sign-in and state (upgrade over 1.x)

- Expected: if 1.x was signed in on this Mac, 2.0 is signed in too, possibly after one keychain prompt
  ("rMirror wants to use your confidential information"). Note whether the prompt appears.
- Expected: no first-sync screen if you had chosen notebooks in 1.x, and nothing is uploaded again.
  Check `~/.config/rmirror/agent.log` for unexpected uploads.

## 3. Permission step (#48)

1. If the window shows "Allow rMirror to read your notebooks": click "Open System Settings", turn rMirror on in
   Full Disk Access, then use "Reopen rMirror" (or let macOS quit and reopen it).
2. Expected: after reopening, the permission screen is gone without further action.
3. If the screen never appears because access was already granted, remove rMirror from Full Disk Access, reopen
   the app and repeat.

## 4. Sign in

1. In Settings → Developer options choose Staging, Apply. Expected: "Sign in again to use this server."
2. Click "Sign in". Expected: the browser opens the rMirror sign-in page; after signing in, a page says you are
   signed in and can close the tab, the address bar shows `/auth/done` with no token in it, and the rMirror window
   moves on by itself.
3. Try it in Safari and in Chrome if both are installed.

## 5. First sync (#37)

1. Expected: "Start with your 3 most recent notebooks" with page counts, one button "Sync N notebooks (M pages)",
   and "Uses M of your … remaining pages this month" under it. The numbers must add up.
2. Click "Choose different notebooks", search, tick something else, go back. Press Return and Esc while the search
   field has focus. Expected: Return does not start a sync, Esc only clears the search.
3. Start the sync. Expected: live progress, then a result screen in plain language; the notebooks appear on the
   website with their text.
4. Close the window during the sync. Expected: the Dock icon disappears, the menu bar line shows progress, the
   sync continues.

## 6. Main window

- "Open rMirror" from the menu bar icon shows status, pages left, and the notebook list.
- Tick one more notebook. Expected: a footer with "… pages to upload" and one "Save and sync" button; the page
  number matches what is then uploaded.
- Untick a notebook and save. Expected: "Save" only, nothing uploads, pages already on the website stay.
- Cmd-Q, Cmd-W, Cmd-M, Cmd-comma, and copy and paste in the search field all work.
- The header is below the title bar, and nothing clips at the smallest window size.
- Write on the tablet, let the reMarkable app sync. Expected: the page uploads by itself within a minute or two.

## 7. Settings

- "Open rMirror when I log in" on, then restart the Mac. Expected: the menu bar icon is back after login without
  a window opening, and syncing works (Full Disk Access still applies).
- Sign out and in again.
- "More options" → page limit: set, remove.

## 8. Quit and leftovers

- Quit from the menu bar. Expected: no `rmirror-core` process and nothing listening on port 5555 afterwards
  (`lsof -nP -iTCP:5555 -sTCP:LISTEN` prints nothing).
- Open the 1.x app while 2.0 runs (or the other way round). Expected: "Another copy of rMirror is running".

## 9. Dashboard (#105, on staging once deployed)

- New account: the setup wizard waits on the Sync step until a notebook really arrives, then offers to open it.
- Refresh the page in the middle of the first sync. Expected: still in the wizard.
- Sidebar shows "Last active …" and turns amber after a day without activity.

## Not testable yet

- Automatic updates: needs a Sparkle key and a published feed.
- Intel: needs the Intel build from the `build-mac-app-intel.yml` workflow, on an Intel Mac.
- macOS 13 to 26.
