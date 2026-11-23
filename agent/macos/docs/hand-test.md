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

### Notebook list: folders, Recent, keyboard

Needs a core that sends `folders` and `parent_uuid` (with an older core the folders are worked out from the paths).

- Folders view: the folders match the tablet, nested, folders first A to Z, folders with no notebooks in them (for example PDF-only folders) are not shown.
  Clicking a folder row opens or closes it; clicking its box ticks every notebook below it (a dash when only some
  are ticked); the footer numbers are the same as ticking those notebooks one by one.
- Close and reopen the window, then quit and start rMirror again. Expected: the same folders are open, the same
  view (Folders or Recent) and the same "Synced only" setting.
- Search: the list goes flat with folder paths; clearing it brings back the outline with the same folders open.
- Recent: newest change first, with "2 hours ago" style times. "Synced only" shows ticked or uploaded notebooks;
  unticking one there does not make it vanish until the filter is switched off and on again.
- Keyboard (not covered by tests): click a row, then Up/Down move the outline, Right opens a folder or steps into
  it, Left closes it or steps out, Space ticks, Return ticks a notebook or opens a folder. While the list has the
  keyboard, Return does not save; click elsewhere or Tab to "Save and sync". Down in the search field moves into
  the list; Return and Esc in the search field still only belong to the field; Cmd-F goes back to the search.
  In Recent, Left and Right do nothing. The highlighted row scrolls into view.
- VoiceOver on a folder row reads e.g. "Work, folder, 2 of 5 selected, expanded"; the Actions rotor offers
  "Tick all in this folder".
- With full keyboard access on (System Settings > Keyboard), Tab reaches the list and a focus ring shows.

### reMarkable app not running

- Signed in, past the first sync, quit the reMarkable app. Expected: within a moment the main window shows "The
  reMarkable app isn't running" with "Open reMarkable", and the menu bar icon gets a dot; its menu shows the same
  line and an "Open reMarkable" item. No notification, no alert, and the rMirror window does not come forward.
- "Open reMarkable" (window or menu) opens the reMarkable app. Expected: the warning and the dot go away by themselves.
- Not shown while signed out, during the first sync, or on the missing-folder or permission screens.
- With the reMarkable app running only in a different macOS user account (fast user switching), the warning still
  shows. That is correct: its files land in that other account.

### Switching server or account (catch-up)

- Signed in and synced, switch server in Settings (e.g. production to staging) and sign in there. Expected: the
  starting screen shows "Checking what's already online…" briefly (the menu bar status line says the same), then the
  main window or the first sync. Afterwards only new or changed pages of ticked notebooks upload by themselves.
- Use an account that has more notebooks online than are ticked on this Mac. Expected: the main window shows "N
  notebooks from this account are already online but not ticked on this Mac." with "Not now" and "Tick them"
  ("1 notebook … is", "Tick it" for one). No line in the menu bar, no dot on the icon, the window does not come
  forward. With the reMarkable app quit as well, both notices show, this one second.
- "Tick them". Expected: those notebooks are ticked in the list, nothing uploads yet, the notice is gone, and the
  footer shows the pages to upload and "Save and sync". After "Save and sync" the number of pages uploaded matches
  that count; pages unchanged since the last sync are not uploaded again.
- "Not now". Expected: the notice is gone, nothing is ticked, and it does not come back after quitting and reopening
  rMirror.

## 7. Settings

- "Open rMirror when I log in" on, then restart the Mac. Expected: the menu bar icon is back after login without
  a window opening, and syncing works (Full Disk Access still applies).
- Sign out and in again.
- "More options" → page limit: set, remove.
- "Open the reMarkable app when rMirror starts" (off by default): turn it on, quit both apps, start rMirror while
  working in another app. Expected: the reMarkable app starts hidden in the background, does not take focus and is
  not added to recent items; no warning shows. Quit the reMarkable app afterwards: rMirror does not start it again
  until rMirror itself is restarted. With the setting off, nothing opens.

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
