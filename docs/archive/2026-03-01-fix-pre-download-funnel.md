# Fix Pre-Download Funnel — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Get new users from signup to first synced notebook in a single sitting by removing the waitlist gate, eliminating the post-signup terms modal, adding a guided setup wizard, and making the download URL dynamic.

**Architecture:** The changes span three components — backend (Clerk webhook + new endpoint), dashboard (signup page + landing page + new SetupWizard component), and agent (auth callback redirect). Backend changes are independent and come first. Dashboard changes build on each other. Agent changes are minimal.

**Tech Stack:** FastAPI (backend), Next.js + React (dashboard), Python + Flask (agent)

**Design doc:** `docs/plans/2026-03-01-fix-pre-download-funnel-design.md`

---

## Task 1: Backend — Set Terms Accepted on User Creation

**Files:**
- Modify: `backend/app/api/webhooks/clerk.py:168-177` (user creation block)
- Modify: `backend/app/api/users.py:17-18` (import constants)
- Test: `backend/tests/unit/test_clerk_webhook_terms.py` (new)

**Context:** When Clerk fires `user.created`, the backend creates a `User` with all legal fields as `NULL`. This means every new user sees a blocking terms modal on their first dashboard visit. Since the signup page already shows "By creating an account, you agree to our Terms of Service and Privacy Policy", we should set the legal fields at creation time. The modal then only fires for legacy users.

**Step 1: Write the failing test**

Create `backend/tests/unit/test_clerk_webhook_terms.py`:

```python
"""Tests for terms acceptance on user creation via Clerk webhook."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from app.api.webhooks.clerk import handle_user_created
from app.api.users import CURRENT_TOS_VERSION, CURRENT_PRIVACY_VERSION
from app.models.user import User


@pytest.mark.asyncio
async def test_new_user_has_terms_accepted(db: Session):
    """New users created via Clerk webhook should have terms pre-accepted."""
    event_data = {
        "data": {
            "id": "clerk_test_terms_123",
            "email_addresses": [
                {"email_address": "newuser@example.com", "id": "email_1"}
            ],
            "primary_email_address_id": "email_1",
            "first_name": "Test",
            "last_name": "User",
        }
    }

    mock_settings = MagicMock()
    mock_settings.beta_signup_enabled = False

    with patch("app.api.webhooks.clerk.get_settings", return_value=mock_settings), \
         patch("app.api.webhooks.clerk.track_event"), \
         patch("app.api.webhooks.clerk.get_email_service") as mock_email:
        mock_email.return_value.send_welcome_email.return_value = None
        await handle_user_created(event_data, db)

    user = db.query(User).filter(User.clerk_user_id == "clerk_test_terms_123").first()
    assert user is not None
    assert user.tos_version == CURRENT_TOS_VERSION
    assert user.privacy_version == CURRENT_PRIVACY_VERSION
    assert user.tos_accepted_at is not None
    assert user.privacy_accepted_at is not None


@pytest.mark.asyncio
async def test_new_user_terms_timestamps_are_recent(db: Session):
    """Terms acceptance timestamps should be set to creation time."""
    before = datetime.utcnow()

    event_data = {
        "data": {
            "id": "clerk_test_terms_456",
            "email_addresses": [
                {"email_address": "newuser2@example.com", "id": "email_2"}
            ],
            "primary_email_address_id": "email_2",
            "first_name": "Another",
            "last_name": "User",
        }
    }

    mock_settings = MagicMock()
    mock_settings.beta_signup_enabled = False

    with patch("app.api.webhooks.clerk.get_settings", return_value=mock_settings), \
         patch("app.api.webhooks.clerk.track_event"), \
         patch("app.api.webhooks.clerk.get_email_service") as mock_email:
        mock_email.return_value.send_welcome_email.return_value = None
        await handle_user_created(event_data, db)

    user = db.query(User).filter(User.clerk_user_id == "clerk_test_terms_456").first()
    assert user.tos_accepted_at >= before
    assert user.privacy_accepted_at >= before
```

**Step 2: Run test to verify it fails**

Run: `cd backend && poetry run pytest tests/unit/test_clerk_webhook_terms.py -v`
Expected: FAIL — `user.tos_version` is `None`, not `"2026-02-20"`

**Step 3: Implement the fix**

In `backend/app/api/webhooks/clerk.py`, add import at top and modify user creation:

Add import near line 10:
```python
from app.api.users import CURRENT_TOS_VERSION, CURRENT_PRIVACY_VERSION
```

Modify the user creation block (lines 168-177) to:
```python
        new_user = User(
            email=primary_email,
            full_name=full_name,
            clerk_user_id=clerk_user_id,
            hashed_password=None,
            is_active=True,
            created_at=datetime.utcnow(),
            # Implicit terms acceptance — signup page shows ToS agreement text
            tos_version=CURRENT_TOS_VERSION,
            tos_accepted_at=datetime.utcnow(),
            privacy_version=CURRENT_PRIVACY_VERSION,
            privacy_accepted_at=datetime.utcnow(),
        )
```

**Step 4: Run test to verify it passes**

Run: `cd backend && poetry run pytest tests/unit/test_clerk_webhook_terms.py -v`
Expected: PASS (2 tests)

**Step 5: Run full test suite**

Run: `cd backend && poetry run pytest -x -q --ignore=test_notion_properties.py`
Expected: All tests pass

**Step 6: Commit**

```bash
cd backend
git add tests/unit/test_clerk_webhook_terms.py app/api/webhooks/clerk.py
git commit -m "feat: set terms accepted on user creation via Clerk webhook

New users signing up via Clerk now have tos_version and privacy_version
set at creation time, since the signup page already shows agreement text.
The blocking TermsAcceptanceModal will only appear for legacy users."
```

---

## Task 2: Backend — Add GET /agents/latest-version Endpoint

**Files:**
- Modify: `backend/app/api/agents.py` (add new endpoint)
- Test: `backend/tests/unit/test_agent_version.py` (new)

**Context:** The dashboard currently hardcodes the agent download URL to `v1.5.2`. This new endpoint returns the latest version and download URL, read from an environment variable. The `release.sh` script will update this when publishing new versions.

**Step 1: Write the failing test**

Create `backend/tests/unit/test_agent_version.py`:

```python
"""Tests for the agent latest-version endpoint."""

from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(db):
    """Create a test client with DB override."""
    from app.main import app
    from app.database import get_db

    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_latest_version_returns_version_info(client):
    """GET /agents/latest-version returns version and download URL."""
    with patch("app.api.agents.get_settings") as mock_settings:
        mock_settings.return_value = MagicMock(
            agent_latest_version="1.5.2",
            agent_download_url_macos="https://example.com/rMirror-1.5.2.dmg",
        )
        response = client.get("/v1/agents/latest-version")

    assert response.status_code == 200
    data = response.json()
    assert data["version"] == "1.5.2"
    assert "macos" in data["platforms"]
    assert data["platforms"]["macos"]["url"] == "https://example.com/rMirror-1.5.2.dmg"


def test_latest_version_no_auth_required(client):
    """The latest-version endpoint should be public (no auth required)."""
    with patch("app.api.agents.get_settings") as mock_settings:
        mock_settings.return_value = MagicMock(
            agent_latest_version="1.5.2",
            agent_download_url_macos="https://example.com/rMirror-1.5.2.dmg",
        )
        response = client.get("/v1/agents/latest-version")

    assert response.status_code == 200
```

**Step 2: Run test to verify it fails**

Run: `cd backend && poetry run pytest tests/unit/test_agent_version.py -v`
Expected: FAIL — 404 (endpoint doesn't exist)

**Step 3: Implement the endpoint**

In `backend/app/api/agents.py`, add at the end of the file (after the existing endpoints):

```python
@router.get("/latest-version")
async def get_latest_agent_version():
    """Return the latest agent version and download URLs.

    This is a public endpoint (no auth required) so the dashboard
    can fetch the download URL before the user is authenticated.
    """
    settings = get_settings()
    version = getattr(settings, "agent_latest_version", "1.5.2")
    macos_url = getattr(
        settings,
        "agent_download_url_macos",
        f"https://f000.backblazeb2.com/file/rmirror-downloads/releases/v{version}/rMirror-{version}.dmg",
    )

    return {
        "version": version,
        "platforms": {
            "macos": {
                "url": macos_url,
                "min_os": "12.0",
            },
        },
    }
```

Also add `get_settings` import if not already present (check top of file).

Add to `backend/app/core/config.py` (the Settings model) two new optional fields:
```python
    agent_latest_version: str = "1.5.2"
    agent_download_url_macos: str = ""
```

**Step 4: Run test to verify it passes**

Run: `cd backend && poetry run pytest tests/unit/test_agent_version.py -v`
Expected: PASS (2 tests)

**Step 5: Run full test suite**

Run: `cd backend && poetry run pytest -x -q --ignore=test_notion_properties.py`
Expected: All tests pass

**Step 6: Commit**

```bash
cd backend
git add app/api/agents.py app/core/config.py tests/unit/test_agent_version.py
git commit -m "feat: add GET /agents/latest-version endpoint

Public endpoint returning agent version and platform-specific download URLs.
Replaces hardcoded DMG URL in dashboard. Reads from AGENT_LATEST_VERSION
and AGENT_DOWNLOAD_URL_MACOS env vars (defaults to B2 CDN pattern)."
```

---

## Task 3: Dashboard — Open Signups (Remove Invite Gate)

**Files:**
- Modify: `dashboard/app/sign-up/[[...sign-up]]/page.tsx` (remove invite validation)
- Modify: `dashboard/app/page.tsx` (landing page CTAs)

**Context:** The signup page currently requires a valid invite token to show the Clerk `<SignUp>` component. Without a token, it shows "Invitation Required" + waitlist form. We're opening signups to everyone.

**Step 1: Simplify the signup page**

Replace the entire `SignUpGate` component in `dashboard/app/sign-up/[[...sign-up]]/page.tsx` with a direct Clerk signup. The file should become:

```tsx
'use client';

import { SignUp } from '@clerk/nextjs';
import Link from 'next/link';

export default function SignUpPage() {
  return (
    <div className="min-h-screen flex items-center justify-center" style={{ background: 'var(--cream)' }}>
      <div className="text-center">
        <div className="mb-8">
          <h1 className="text-3xl font-bold mb-2" style={{ color: 'var(--warm-charcoal)', fontFamily: 'var(--font-display)' }}>
            Join rMirror
          </h1>
          <div className="inline-block px-2 py-0.5 rounded text-xs font-medium mb-2" style={{ background: 'var(--terracotta)', color: 'white' }}>
            BETA
          </div>
          <p style={{ color: 'var(--warm-gray)' }}>
            Your reMarkable notebooks, searchable everywhere
          </p>
        </div>
        <SignUp
          appearance={{
            elements: {
              rootBox: 'mx-auto',
              card: 'shadow-lg',
            },
          }}
        />
        <p className="mt-6 text-center text-sm max-w-sm mx-auto" style={{ color: 'var(--warm-gray)' }}>
          By creating an account, you agree to our{' '}
          <Link href="/legal/terms" className="underline hover:opacity-80" style={{ color: 'var(--terracotta)' }}>
            Terms of Service
          </Link>{' '}
          and{' '}
          <Link href="/legal/privacy" className="underline hover:opacity-80" style={{ color: 'var(--terracotta)' }}>
            Privacy Policy
          </Link>.
        </p>
      </div>
    </div>
  );
}
```

This removes: the `validateInviteToken` call, the loading spinner, the "Invitation Required" card, the waitlist form, and all associated state.

**Step 2: Update landing page CTA**

In `dashboard/app/page.tsx`, change the "Request Early Access" button (around lines 217-230 for desktop and lines 336-350 for mobile) from:

```tsx
<a
  href="#waitlist"
  onClick={scrollToWaitlist}
  ...
>
  Request Early Access
  <ArrowRight className="w-5 h-5" />
</a>
```

to:

```tsx
<a
  href="/sign-up"
  ...
>
  Sign Up Free
  <ArrowRight className="w-5 h-5" />
</a>
```

Do this for both the desktop (line ~220) and mobile (line ~340) versions.

**Step 3: Replace waitlist section with simple CTA**

In `dashboard/app/page.tsx`, replace the waitlist form section (lines ~857-932, inside `{!isSignedIn && (...)}`) with a simpler call to action:

```tsx
{!isSignedIn && (
  <section className="py-20 lg:py-28">
    <div className="max-w-2xl mx-auto text-center px-4">
      <h2 className="text-3xl lg:text-4xl font-bold mb-4" style={{ color: 'var(--warm-charcoal)', fontFamily: 'var(--font-display)' }}>
        Ready to Unlock Your Notes?
      </h2>
      <p className="text-lg mb-8" style={{ color: 'var(--warm-gray)' }}>
        Sign up for free and start syncing your reMarkable notebooks in minutes.
      </p>
      <a
        href="/sign-up"
        className="inline-flex items-center justify-center gap-2 px-8 py-4 rounded-lg text-lg font-semibold transition-all hover:scale-105"
        style={{ background: 'var(--terracotta)', color: 'white', boxShadow: 'var(--shadow-md)' }}
      >
        Sign Up Free
        <ArrowRight className="w-5 h-5" />
      </a>
    </div>
  </section>
)}
```

Remove the `scrollToWaitlist` function, `handleSubmit`, and all waitlist-related state (`email`, `name`, `isSubmitting`, `showSuccess`, `showError`).

**Step 4: Clean up unused imports**

Remove `validateInviteToken` from `dashboard/lib/api.ts` imports in the signup page (it's no longer used there). The function can stay in `api.ts` for now — the admin waitlist page may still use it.

**Step 5: Test manually**

Run: `cd dashboard && npm run build`
Expected: Build succeeds with no errors.

Then: `npm run dev` and visit `http://localhost:3000/sign-up` — should show Clerk signup directly, no "Invitation Required" message.

Visit `http://localhost:3000` — CTA should say "Sign Up Free" and link to `/sign-up`.

**Step 6: Commit**

```bash
cd dashboard
git add app/sign-up/\[\[...sign-up\]\]/page.tsx app/page.tsx
git commit -m "feat: open signups by removing beta waitlist gate

- Signup page shows Clerk signup directly (no invite token required)
- Landing page CTA changed from 'Request Early Access' to 'Sign Up Free'
- Waitlist form replaced with direct signup link
- Existing waitlist data preserved (no migration needed)"
```

---

## Task 4: Dashboard — Add API Helper for Agent Version

**Files:**
- Modify: `dashboard/lib/api.ts` (add `getLatestAgentVersion`)

**Context:** Add a function to call the new `/agents/latest-version` endpoint. This is used by the setup wizard to get the dynamic download URL.

**Step 1: Add the function**

In `dashboard/lib/api.ts`, add near the existing agent functions (around line 186):

```typescript
export interface AgentVersionInfo {
  version: string;
  platforms: {
    macos?: {
      url: string;
      min_os: string;
    };
    windows?: {
      url: string;
    };
  };
}

export async function getLatestAgentVersion(): Promise<AgentVersionInfo> {
  const response = await fetch(`${API_URL}/agents/latest-version`);
  return handleApiResponse<AgentVersionInfo>(response);
}
```

Note: This is a public endpoint — no auth token needed.

**Step 2: Commit**

```bash
cd dashboard
git add lib/api.ts
git commit -m "feat: add getLatestAgentVersion API helper

Calls GET /agents/latest-version to get dynamic download URL
instead of hardcoding the DMG version in the dashboard."
```

---

## Task 5: Dashboard — Create SetupWizard Component

**Files:**
- Create: `dashboard/app/dashboard/components/SetupWizard.tsx`

**Context:** This is the core UX improvement. A full-screen guided wizard that replaces the empty dashboard + onboarding checklist for new users. It walks them through: welcome → download → install & connect (with live polling) → sync → done.

**Step 1: Create the component**

Create `dashboard/app/dashboard/components/SetupWizard.tsx`:

```tsx
'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { Download, CheckCircle, Monitor, Loader2, ArrowRight, ArrowLeft, BookOpen, ExternalLink, FolderOpen, RefreshCw } from 'lucide-react';
import { getLatestAgentVersion, AgentVersionInfo, getAgentStatus } from '@/lib/api';

interface SetupWizardProps {
  token: string | null;
  getToken: () => Promise<string | null>;
  isDevelopmentMode: boolean;
  onComplete: () => void;
  onDismiss: () => void;
}

type WizardStep = 1 | 2 | 3 | 4;

export default function SetupWizard({
  token,
  getToken,
  isDevelopmentMode,
  onComplete,
  onDismiss,
}: SetupWizardProps) {
  const [currentStep, setCurrentStep] = useState<WizardStep>(1);
  const [agentVersion, setAgentVersion] = useState<AgentVersionInfo | null>(null);
  const [agentConnected, setAgentConnected] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const pollingRef = useRef<NodeJS.Timeout | null>(null);

  // Fetch latest agent version on mount
  useEffect(() => {
    getLatestAgentVersion()
      .then(setAgentVersion)
      .catch((err) => console.error('Failed to fetch agent version:', err));
  }, []);

  // Poll for agent connection in step 2
  useEffect(() => {
    if (currentStep !== 2) {
      if (pollingRef.current) clearInterval(pollingRef.current);
      return;
    }

    const checkAgent = async () => {
      try {
        const authToken = isDevelopmentMode
          ? process.env.NEXT_PUBLIC_DEV_AUTH_TOKEN || localStorage.getItem('dev_auth_token') || ''
          : await getToken();
        if (!authToken) return;

        const status = await getAgentStatus(authToken);
        if (status.has_agent_connected) {
          setAgentConnected(true);
          if (pollingRef.current) clearInterval(pollingRef.current);
          // Auto-advance after brief celebration
          setTimeout(() => setCurrentStep(3), 1500);
        }
      } catch (err) {
        // Silently retry on next poll
      }
    };

    checkAgent(); // Check immediately
    pollingRef.current = setInterval(checkAgent, 5000);

    return () => {
      if (pollingRef.current) clearInterval(pollingRef.current);
    };
  }, [currentStep, getToken, isDevelopmentMode]);

  const handleDownload = useCallback(() => {
    if (!agentVersion?.platforms.macos?.url) return;
    setDownloading(true);
    window.open(agentVersion.platforms.macos.url, '_blank');
    // Move to step 2 after a short delay
    setTimeout(() => {
      setCurrentStep(2);
      setDownloading(false);
    }, 1000);
  }, [agentVersion]);

  const macosUrl = agentVersion?.platforms.macos?.url;
  const version = agentVersion?.version;

  return (
    <div className="min-h-[60vh] flex flex-col items-center justify-center px-4 py-12">
      {/* Progress indicator */}
      <div className="flex items-center gap-2 mb-12">
        {[1, 2, 3, 4].map((step) => (
          <div key={step} className="flex items-center gap-2">
            <div
              className="w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium transition-all"
              style={{
                background: currentStep >= step ? 'var(--terracotta)' : 'var(--warm-bg)',
                color: currentStep >= step ? 'white' : 'var(--warm-gray)',
                border: currentStep >= step ? 'none' : '2px solid var(--warm-border)',
              }}
            >
              {currentStep > step ? <CheckCircle className="w-4 h-4" /> : step}
            </div>
            {step < 4 && (
              <div
                className="w-8 h-0.5"
                style={{ background: currentStep > step ? 'var(--terracotta)' : 'var(--warm-border)' }}
              />
            )}
          </div>
        ))}
      </div>

      {/* Step content */}
      <div className="max-w-lg w-full">
        {currentStep === 1 && (
          <div className="text-center">
            <div className="w-16 h-16 rounded-2xl flex items-center justify-center mx-auto mb-6" style={{ background: 'var(--terracotta-light, #f5e6e5)' }}>
              <BookOpen className="w-8 h-8" style={{ color: 'var(--terracotta)' }} />
            </div>
            <h2 className="text-2xl font-bold mb-3" style={{ color: 'var(--warm-charcoal)', fontFamily: 'var(--font-display)' }}>
              Welcome to rMirror
            </h2>
            <p className="text-base mb-8" style={{ color: 'var(--warm-gray)' }}>
              Your reMarkable notebooks, searchable and synced to Notion.
              Let's get you set up — it only takes a few minutes.
            </p>

            <div className="rounded-xl p-6 mb-6" style={{ background: 'var(--warm-bg)', border: '1px solid var(--warm-border)' }}>
              <p className="text-sm font-medium mb-4" style={{ color: 'var(--warm-charcoal)' }}>
                Choose your platform
              </p>
              <div className="flex gap-3 justify-center">
                <button
                  onClick={handleDownload}
                  disabled={!macosUrl || downloading}
                  className="flex items-center gap-2 px-6 py-3 rounded-lg font-medium transition-all hover:scale-105 disabled:opacity-50 disabled:hover:scale-100"
                  style={{ background: 'var(--terracotta)', color: 'white' }}
                >
                  {downloading ? (
                    <Loader2 className="w-5 h-5 animate-spin" />
                  ) : (
                    <Download className="w-5 h-5" />
                  )}
                  Download for macOS
                </button>
              </div>
              {version && (
                <p className="text-xs mt-3" style={{ color: 'var(--warm-gray)' }}>
                  Version {version} &middot; macOS 12+
                </p>
              )}
              <p className="text-xs mt-2" style={{ color: 'var(--warm-gray)' }}>
                Windows support coming soon
              </p>
            </div>

            <button
              onClick={onDismiss}
              className="text-sm underline hover:opacity-80"
              style={{ color: 'var(--warm-gray)' }}
            >
              Skip setup
            </button>
          </div>
        )}

        {currentStep === 2 && (
          <div className="text-center">
            <div className="w-16 h-16 rounded-2xl flex items-center justify-center mx-auto mb-6" style={{ background: agentConnected ? 'var(--sage-light, #e8f0ea)' : 'var(--terracotta-light, #f5e6e5)' }}>
              {agentConnected ? (
                <CheckCircle className="w-8 h-8" style={{ color: 'var(--sage-green)' }} />
              ) : (
                <Monitor className="w-8 h-8" style={{ color: 'var(--terracotta)' }} />
              )}
            </div>

            {agentConnected ? (
              <>
                <h2 className="text-2xl font-bold mb-3" style={{ color: 'var(--warm-charcoal)', fontFamily: 'var(--font-display)' }}>
                  Agent Connected!
                </h2>
                <p className="text-base mb-6" style={{ color: 'var(--sage-green)' }}>
                  rMirror is running and connected to your account.
                </p>
              </>
            ) : (
              <>
                <h2 className="text-2xl font-bold mb-3" style={{ color: 'var(--warm-charcoal)', fontFamily: 'var(--font-display)' }}>
                  Install & Connect
                </h2>
                <p className="text-base mb-8" style={{ color: 'var(--warm-gray)' }}>
                  Follow these steps to get the agent running.
                </p>
              </>
            )}

            {!agentConnected && (
              <div className="text-left rounded-xl p-6 mb-6" style={{ background: 'var(--warm-bg)', border: '1px solid var(--warm-border)' }}>
                <ol className="space-y-4">
                  <li className="flex gap-3">
                    <span className="flex-shrink-0 w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold" style={{ background: 'var(--terracotta)', color: 'white' }}>1</span>
                    <div>
                      <p className="font-medium" style={{ color: 'var(--warm-charcoal)' }}>Open the downloaded DMG</p>
                      <p className="text-sm" style={{ color: 'var(--warm-gray)' }}>Double-click <code>rMirror-{version}.dmg</code> in your Downloads</p>
                    </div>
                  </li>
                  <li className="flex gap-3">
                    <span className="flex-shrink-0 w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold" style={{ background: 'var(--terracotta)', color: 'white' }}>2</span>
                    <div>
                      <p className="font-medium" style={{ color: 'var(--warm-charcoal)' }}>Drag to Applications</p>
                      <p className="text-sm" style={{ color: 'var(--warm-gray)' }}>Drag the rMirror icon to the Applications folder</p>
                    </div>
                  </li>
                  <li className="flex gap-3">
                    <span className="flex-shrink-0 w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold" style={{ background: 'var(--terracotta)', color: 'white' }}>3</span>
                    <div>
                      <p className="font-medium" style={{ color: 'var(--warm-charcoal)' }}>Launch rMirror</p>
                      <p className="text-sm" style={{ color: 'var(--warm-gray)' }}>Open it from Applications — it will appear in your menu bar</p>
                    </div>
                  </li>
                  <li className="flex gap-3">
                    <span className="flex-shrink-0 w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold" style={{ background: 'var(--terracotta)', color: 'white' }}>4</span>
                    <div>
                      <p className="font-medium" style={{ color: 'var(--warm-charcoal)' }}>Sign in</p>
                      <p className="text-sm" style={{ color: 'var(--warm-gray)' }}>The agent will open a browser window — sign in with your account</p>
                    </div>
                  </li>
                </ol>
              </div>
            )}

            {!agentConnected && (
              <div className="flex items-center justify-center gap-2 mb-6" style={{ color: 'var(--warm-gray)' }}>
                <Loader2 className="w-4 h-4 animate-spin" />
                <span className="text-sm">Waiting for agent to connect...</span>
              </div>
            )}

            <div className="flex justify-between items-center">
              <button
                onClick={() => setCurrentStep(1)}
                className="flex items-center gap-1 text-sm hover:opacity-80"
                style={{ color: 'var(--warm-gray)' }}
              >
                <ArrowLeft className="w-4 h-4" /> Back
              </button>
              {!agentConnected && (
                <button
                  onClick={() => setCurrentStep(3)}
                  className="text-sm underline hover:opacity-80"
                  style={{ color: 'var(--warm-gray)' }}
                >
                  I already have the agent installed
                </button>
              )}
            </div>
          </div>
        )}

        {currentStep === 3 && (
          <div className="text-center">
            <div className="w-16 h-16 rounded-2xl flex items-center justify-center mx-auto mb-6" style={{ background: 'var(--terracotta-light, #f5e6e5)' }}>
              <FolderOpen className="w-8 h-8" style={{ color: 'var(--terracotta)' }} />
            </div>
            <h2 className="text-2xl font-bold mb-3" style={{ color: 'var(--warm-charcoal)', fontFamily: 'var(--font-display)' }}>
              Sync Your Notebooks
            </h2>
            <p className="text-base mb-8" style={{ color: 'var(--warm-gray)' }}>
              The agent will sync your reMarkable notebooks to the cloud.
              Open the agent from your menu bar and click "Initial Sync" to get started.
            </p>

            <div className="rounded-xl p-6 mb-6" style={{ background: 'var(--warm-bg)', border: '1px solid var(--warm-border)' }}>
              <p className="text-sm" style={{ color: 'var(--warm-gray)' }}>
                Your free tier includes <strong>30 pages</strong> of OCR transcription per month.
                The agent will sync notebook structure immediately, and OCR will process your most recent pages first.
              </p>
            </div>

            <button
              onClick={() => setCurrentStep(4)}
              className="flex items-center gap-2 px-6 py-3 rounded-lg font-medium transition-all hover:scale-105 mx-auto"
              style={{ background: 'var(--terracotta)', color: 'white' }}
            >
              Continue
              <ArrowRight className="w-4 h-4" />
            </button>

            <div className="mt-4">
              <button
                onClick={() => setCurrentStep(2)}
                className="flex items-center gap-1 text-sm hover:opacity-80 mx-auto"
                style={{ color: 'var(--warm-gray)' }}
              >
                <ArrowLeft className="w-4 h-4" /> Back
              </button>
            </div>
          </div>
        )}

        {currentStep === 4 && (
          <div className="text-center">
            <div className="w-16 h-16 rounded-2xl flex items-center justify-center mx-auto mb-6" style={{ background: 'var(--sage-light, #e8f0ea)' }}>
              <CheckCircle className="w-8 h-8" style={{ color: 'var(--sage-green)' }} />
            </div>
            <h2 className="text-2xl font-bold mb-3" style={{ color: 'var(--warm-charcoal)', fontFamily: 'var(--font-display)' }}>
              You're All Set!
            </h2>
            <p className="text-base mb-8" style={{ color: 'var(--warm-gray)' }}>
              Your notebooks will appear here as they sync.
              The agent runs quietly in your menu bar — you don't need to keep this page open.
            </p>

            <div className="flex flex-col gap-3 items-center">
              <button
                onClick={onComplete}
                className="flex items-center gap-2 px-6 py-3 rounded-lg font-medium transition-all hover:scale-105"
                style={{ background: 'var(--terracotta)', color: 'white' }}
              >
                Go to Dashboard
                <ArrowRight className="w-4 h-4" />
              </button>
              <a
                href="/integrations/notion/setup"
                className="flex items-center gap-1 text-sm hover:opacity-80"
                style={{ color: 'var(--terracotta)' }}
              >
                Connect Notion <ExternalLink className="w-3 h-3" />
              </a>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
```

**Step 2: Verify it builds**

Run: `cd dashboard && npm run build`
Expected: Build succeeds (component is created but not yet wired in)

**Step 3: Commit**

```bash
cd dashboard
git add app/dashboard/components/SetupWizard.tsx
git commit -m "feat: add SetupWizard component for guided onboarding

4-step wizard: Welcome + Download → Install & Connect (polls agent status
every 5s, auto-advances on connection) → Sync Notebooks → Done.
Uses dynamic download URL from /agents/latest-version endpoint.
Follows Moleskine design system."
```

---

## Task 6: Dashboard — Integrate SetupWizard into Dashboard Page

**Files:**
- Modify: `dashboard/app/dashboard/page.tsx`

**Context:** Wire the SetupWizard into the dashboard page. Show it when: user has no notebooks AND hasn't dismissed the wizard. When complete, transition to the normal dashboard view.

**Step 1: Add wizard state and import**

At the top of `dashboard/app/dashboard/page.tsx`, add the import:

```typescript
import SetupWizard from './components/SetupWizard';
```

Add state inside the component (near the other useState calls):

```typescript
const [wizardCompleted, setWizardCompleted] = useState(false);
```

**Step 2: Add wizard rendering logic**

Replace the empty-state block (around lines 879-900, the `notebooks.length === 0` branch) with the wizard:

Replace:
```tsx
} : notebooks.length === 0 ? (
  <div className="text-center py-12 rounded-lg max-w-2xl mx-auto" ...>
    ...Download rMirror Agent for macOS...
  </div>
```

With:
```tsx
} : notebooks.length === 0 && !wizardCompleted && onboarding && !onboarding.onboarding_dismissed ? (
  <SetupWizard
    token={null}
    getToken={async () => {
      if (isDevelopmentMode) {
        return process.env.NEXT_PUBLIC_DEV_AUTH_TOKEN || localStorage.getItem('dev_auth_token') || '';
      }
      return await getToken();
    }}
    isDevelopmentMode={isDevelopmentMode}
    onComplete={() => {
      setWizardCompleted(true);
      fetchNotebooks();
    }}
    onDismiss={() => {
      setWizardCompleted(true);
      handleDismissOnboarding();
    }}
  />
) : notebooks.length === 0 ? (
  <div className="text-center py-12 rounded-lg max-w-2xl mx-auto" style={{ background: 'var(--warm-bg)', border: '1px solid var(--warm-border)' }}>
    <BookOpen className="w-20 h-20 mx-auto mb-4" style={{ color: 'var(--warm-gray)', opacity: 0.3 }} />
    <h3 className="text-xl font-semibold mb-2" style={{ color: 'var(--warm-charcoal)' }}>No notebooks yet</h3>
    <p className="mb-6" style={{ color: 'var(--warm-gray)' }}>
      Download and install the rMirror Agent to sync your reMarkable notebooks.
    </p>
    <button onClick={handleDownloadClick} className="px-6 py-3 rounded-lg font-medium" style={{ background: 'var(--terracotta)', color: 'white' }}>
      Download rMirror Agent for macOS
    </button>
  </div>
```

This way:
- New users who haven't dismissed onboarding see the wizard
- Users who dismiss the wizard (or completed it before) see a simpler empty state
- Users with notebooks see the normal notebook grid

**Step 3: Hide onboarding checklist when wizard is active**

Modify the onboarding checklist rendering condition (around line 855) from:

```tsx
{onboarding && !onboarding.onboarding_dismissed && !isSearchMode && (
```

to:

```tsx
{onboarding && !onboarding.onboarding_dismissed && !isSearchMode && (notebooks.length > 0 || wizardCompleted) && (
```

This prevents the checklist and wizard from showing simultaneously.

**Step 4: Build and test**

Run: `cd dashboard && npm run build`
Expected: Build succeeds.

Run: `npm run dev` and test with a fresh account (or by clearing the onboarding dismissed flag):
- With no notebooks: should see the 4-step wizard
- After completing wizard: should see the normal dashboard
- With existing notebooks: should see notebooks + onboarding checklist as before

**Step 5: Commit**

```bash
cd dashboard
git add app/dashboard/page.tsx
git commit -m "feat: integrate SetupWizard into dashboard for new users

New users with no notebooks see a guided 4-step wizard instead of
the empty dashboard. Wizard replaces both the empty-state card and
the onboarding checklist. Users can skip, and the checklist returns
for those who have some notebooks but haven't completed all steps."
```

---

## Task 7: Agent — Redirect Auth Callback to Dashboard

**Files:**
- Modify: `agent/app/web/routes.py:260-318` (auth callback route)

**Context:** After successful authentication, the agent currently renders `auth_result.html` (a success page on localhost:5555 that auto-redirects to the agent's web UI). We want it to redirect to the dashboard instead, so the user lands back on the setup wizard's Step 2 which will detect the agent connection.

**Step 1: Modify the auth callback**

In `agent/app/web/routes.py`, change the success return in the `/auth/callback` route (around line 316):

From:
```python
        return render_template("auth_result.html", success=True, message="Successfully authenticated with Clerk!")
```

To:
```python
        # Redirect to dashboard - the setup wizard will detect agent connection
        dashboard_url = config.api.url.replace("/api/v1", "").replace("/api", "")
        if not dashboard_url or "localhost:8000" in dashboard_url:
            dashboard_url = "https://rmirror.io"
        return redirect(f"{dashboard_url}/dashboard")
```

Add `redirect` to the Flask imports at the top of the file:
```python
from flask import ..., redirect
```

**Step 2: Test locally**

Run: `cd agent && poetry run python -m app.main --foreground --debug`
Simulate auth callback: `curl -v "http://localhost:5555/auth/callback?token=test123"` (will fail to register but should attempt redirect)
Expected: 302 redirect to dashboard URL

**Step 3: Commit**

```bash
cd agent
git add app/web/routes.py
git commit -m "feat: redirect auth callback to dashboard instead of local page

After successful authentication, the agent now redirects the browser
to the dashboard (rmirror.io/dashboard) instead of rendering a local
success page. This lands the user on the setup wizard which will
detect the agent connection via polling."
```

---

## Task 8: Update handleDownloadClick to Use Dynamic URL

**Files:**
- Modify: `dashboard/app/dashboard/page.tsx`

**Context:** The existing `handleDownloadClick` function (used by the onboarding checklist's "Download Agent" button and the fallback empty state) still hardcodes the DMG URL. Update it to use the dynamic endpoint.

**Step 1: Add state for agent version**

Add state near the other useState calls:
```typescript
const [agentVersionInfo, setAgentVersionInfo] = useState<AgentVersionInfo | null>(null);
```

Add import:
```typescript
import { getLatestAgentVersion, AgentVersionInfo } from '@/lib/api';
```

Fetch on mount (inside the existing useEffect or a new one):
```typescript
useEffect(() => {
  getLatestAgentVersion()
    .then(setAgentVersionInfo)
    .catch((err) => console.error('Failed to fetch agent version:', err));
}, []);
```

**Step 2: Update handleDownloadClick**

Replace the function (lines ~203-214):

```typescript
const handleDownloadClick = async () => {
  if (effectiveIsSignedIn) {
    const token = isDevelopmentMode
      ? process.env.NEXT_PUBLIC_DEV_AUTH_TOKEN || localStorage.getItem('dev_auth_token') || ''
      : await getToken();
    if (token) {
      await trackAgentDownload(token);
    }
  }
  trackEvent({ name: 'agent_downloaded' });
  const downloadUrl = agentVersionInfo?.platforms.macos?.url
    || 'https://f000.backblazeb2.com/file/rmirror-downloads/releases/v1.5.2/rMirror-1.5.2.dmg';
  window.open(downloadUrl, '_blank');
};
```

Note: Changed from `window.location.href` to `window.open` so the user stays on the dashboard page (no navigation away).

**Step 3: Build and test**

Run: `cd dashboard && npm run build`
Expected: Build succeeds.

**Step 4: Commit**

```bash
cd dashboard
git add app/dashboard/page.tsx
git commit -m "feat: use dynamic download URL from /agents/latest-version

handleDownloadClick now fetches the agent version from the backend
instead of hardcoding v1.5.2. Also changed to window.open() so
the user stays on the dashboard during download."
```

---

## Task Summary

| # | Component | Description | Depends on |
|---|-----------|-------------|------------|
| 1 | Backend | Set terms accepted on user creation | — |
| 2 | Backend | Add GET /agents/latest-version endpoint | — |
| 3 | Dashboard | Open signups (remove invite gate) | — |
| 4 | Dashboard | Add API helper for agent version | Task 2 |
| 5 | Dashboard | Create SetupWizard component | Task 4 |
| 6 | Dashboard | Integrate SetupWizard into dashboard | Task 5 |
| 7 | Agent | Redirect auth callback to dashboard | — |
| 8 | Dashboard | Update handleDownloadClick to use dynamic URL | Task 4 |

Tasks 1, 2, 3, and 7 are independent and can be done in parallel.
Tasks 4-6 must be sequential.
Task 8 depends on Task 4 but is independent of 5-6.

## Post-Implementation

After all tasks are complete:
1. Deploy backend changes to production first (so endpoints exist)
2. Deploy dashboard changes
3. Release agent update (redirect change) — this can wait for next agent release
4. Update `release.sh` to set `AGENT_LATEST_VERSION` env var on the backend after each release
5. Test the full flow: new signup → wizard → download → install → connect → sync
