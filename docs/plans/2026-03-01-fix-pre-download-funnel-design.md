# Fix Pre-Download Funnel

**Date**: 2026-03-01
**Status**: Approved
**Phase**: 1 of 4 (Funnel Fix > Agent UX > Tauri Rewrite > Windows Support)

## Problem

Most beta users sign up but never download the agent. The drop-off happens before users interact with the agent at all. Root causes:

1. **Waitlist creates two friction moments**: Sign up for waitlist, wait days/weeks for invite, then come back and sign up again. Initial excitement has faded by the time the invite arrives.
2. **Terms modal blocks the dashboard immediately**: The first thing after signup is a full-screen blocking modal over an empty dashboard, before users see any value.
3. **No post-download guidance**: Clicking "Download Agent" navigates away to a raw B2 CDN URL with zero instructions on installation, permissions, or configuration.
4. **No live feedback**: The onboarding checklist doesn't auto-update when the agent connects. Users must manually refresh.
5. **Hardcoded download URL**: The DMG URL is hardcoded to v1.5.2 in the dashboard page source.

## Solution

### 1. Open Signups (Remove Beta Waitlist)

Remove the invite-token gate from the signup page. Show the Clerk `<SignUp>` component directly to all visitors.

**Changes**:
- `dashboard/app/sign-up/[[...sign-up]]/page.tsx`: Remove invite token validation, always show Clerk signup
- `dashboard/app/page.tsx` (landing): Replace "Request Early Access" CTA with "Sign Up Free", remove waitlist form
- Keep "BETA" badge in UI so users know it's early
- Keep existing waitlist data (don't delete entries)
- The 30 pages/month free tier quota already limits abuse

### 2. Implicit Terms Acceptance on Signup

Set `tos_version` and `privacy_version` in the Clerk `user.created` webhook handler. The signup page already shows "By creating an account, you agree to our Terms of Service and Privacy Policy" — this is legally sufficient as implicit acceptance.

**Changes**:
- `backend/app/api/webhooks/clerk.py`: In the `user.created` handler, set `tos_version = CURRENT_TOS_VERSION`, `tos_accepted_at = utcnow()`, `privacy_version = CURRENT_PRIVACY_VERSION`, `privacy_accepted_at = utcnow()` on the new User record
- The existing `TermsAcceptanceModal` continues to work for legacy users who signed up before terms existed (their fields are still NULL)
- No changes to the modal component itself

### 3. Setup Wizard (Replaces Empty Dashboard)

A full-screen guided setup wizard that takes over the dashboard view until first sync completes. Replaces both the onboarding checklist and the empty-state card.

**Trigger condition**: Show wizard when user has no notebooks AND has not dismissed it.

**Step 1: Welcome**
- Brief value prop: "Your reMarkable notebooks, searchable and synced"
- Screenshot/illustration of a synced notebook
- Platform selector: macOS (active) | Windows (coming soon, with email capture)
- "Download for macOS" button (fetches URL from backend)

**Step 2: Install & Connect**
- Visual step-by-step instructions:
  1. Open the downloaded DMG
  2. Drag rMirror to Applications
  3. Launch rMirror (it will appear in the menu bar)
  4. Sign in when the agent opens in your browser
- Screenshots or GIF for each sub-step
- Live agent status indicator: polls `GET /agents/status` every 5 seconds
- When agent connects: green checkmark animation, auto-advance to Step 3
- "Skip" link for users who already have the agent

**Step 3: Sync Your Notebooks**
- Shows notebook tree from agent (via backend, after agent has scanned the reMarkable folder)
- "Sync All" toggle or individual notebook selection
- Page limit input (default to free tier quota)
- "Start Sync" button
- Progress indicator during sync

**Step 4: You're All Set**
- Celebratory message
- Shows first synced notebook preview
- Subtle CTA: "Connect Notion for automatic sync" (links to integrations)
- "Go to Dashboard" button → transitions to normal dashboard view

**Component**: `dashboard/app/dashboard/components/SetupWizard.tsx` (new)

**Changes**:
- `dashboard/app/dashboard/page.tsx`: Render `SetupWizard` when user has no notebooks and hasn't dismissed wizard. Remove the empty-state card.
- The existing `OnboardingChecklist` can be kept for returning users who dismissed the wizard but haven't completed all steps.

### 4. Dynamic Download URL

Replace the hardcoded DMG URL with a backend endpoint.

**New endpoint**: `GET /v1/agents/latest-version`
```json
{
  "version": "1.5.2",
  "platforms": {
    "macos": {
      "url": "https://f000.backblazeb2.com/file/rmirror-downloads/releases/v1.5.2/rMirror-1.5.2.dmg",
      "min_os": "12.0"
    }
  }
}
```

**Changes**:
- `backend/app/api/agents.py`: New endpoint, reads from environment variable or config
- `dashboard/lib/api.ts`: New `getLatestAgentVersion()` function
- `dashboard/app/dashboard/page.tsx`: Replace hardcoded URL with API call
- `agent/release.sh`: Update to also set the version in backend config after B2 upload

### 5. Agent-Side Quick Wins

Minimal agent changes to support the wizard flow:

- **Auto-register on auth**: Call `/agents/register` immediately after successful authentication in the auth callback, not just when file watcher starts
- **Redirect to dashboard after auth**: After successful auth callback, redirect browser to `https://rmirror.io/dashboard` instead of `localhost:5555`, so the user lands back on the setup wizard Step 2 which will detect the agent connection
- **Auto-detect reMarkable folder**: Already has the default macOS path. Verify it exists on startup and skip the config step.

**Changes**:
- `agent/app/web/routes.py`: Change auth callback redirect target
- `agent/app/sync/cloud_sync.py` or `agent/app/main.py`: Register agent immediately on auth

## What This Does NOT Include

Explicitly deferred to later phases:

- **Phase 2: Agent UX overhaul** — Improve the localhost:5555 web UI (better status, sync progress, error messaging). Still Python + Flask.
- **Phase 3: Tauri rewrite** — Replace Python agent with Tauri app (Rust + web view). Native window, system tray, auto-updater, cross-platform binary.
- **Phase 4: Windows support** — Either via Tauri (Phase 3) or Python + pystray + NSIS as a stopgap.

## Files Changed

### Dashboard (Primary)
| File | Action | Description |
|------|--------|-------------|
| `app/sign-up/[[...sign-up]]/page.tsx` | Modify | Remove invite-token gate |
| `app/page.tsx` | Modify | Replace waitlist CTA with direct signup |
| `app/dashboard/components/SetupWizard.tsx` | Create | Full-screen guided setup wizard |
| `app/dashboard/page.tsx` | Modify | Render wizard for new users, remove empty-state |
| `lib/api.ts` | Modify | Add `getLatestAgentVersion()` |

### Backend
| File | Action | Description |
|------|--------|-------------|
| `app/api/webhooks/clerk.py` | Modify | Set terms accepted on user creation |
| `app/api/agents.py` | Modify | Add `GET /v1/agents/latest-version` endpoint |

### Agent (Minimal)
| File | Action | Description |
|------|--------|-------------|
| `app/web/routes.py` | Modify | Redirect auth callback to dashboard |
| `app/main.py` or `app/sync/cloud_sync.py` | Modify | Register agent immediately on auth |

## Success Criteria

- New user can go from landing page to first synced notebook in < 10 minutes
- No more than 2 "unexpected" screens between signup and seeing the setup wizard
- Agent detection in wizard Step 2 works within 10 seconds of agent connecting
- Download URL is always current (no hardcoded version)
