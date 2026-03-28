'use client';

import { useAuth, useUser, SignIn, useClerk } from '@clerk/nextjs';
import { useSearchParams } from 'next/navigation';
import { useState, useCallback, Suspense } from 'react';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'https://rmirror.io/api/v1';

function validateCallbackUrl(url: string): boolean {
  try {
    const parsed = new URL(url);
    return ['localhost', '127.0.0.1'].includes(parsed.hostname);
  } catch {
    return false;
  }
}

type BridgeState =
  | { phase: 'confirm' }
  | { phase: 'exchanging'; message: string }
  | { phase: 'error'; message: string };

function AgentAuthBridgeInner() {
  const { isLoaded, isSignedIn, getToken } = useAuth();
  const { user } = useUser();
  const { signOut } = useClerk();
  const searchParams = useSearchParams();
  const callbackUrl = searchParams.get('callback') || '';

  const [state, setState] = useState<BridgeState>({ phase: 'confirm' });

  const displayName = user?.firstName || user?.username || 'User';
  const email = user?.primaryEmailAddress?.emailAddress || '';

  const exchangeAndRedirect = useCallback(async () => {
    if (!validateCallbackUrl(callbackUrl)) {
      setState({ phase: 'error', message: 'Invalid callback URL: must be localhost' });
      return;
    }

    try {
      setState({ phase: 'exchanging', message: 'Getting authentication token...' });

      const clerkToken = await getToken();
      if (!clerkToken) {
        setState({ phase: 'error', message: 'Failed to get session token. Please try again.' });
        return;
      }

      setState({ phase: 'exchanging', message: 'Exchanging for agent token...' });

      const response = await fetch(`${API_URL}/auth/agent-token`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${clerkToken}`,
          'Content-Type': 'application/json',
        },
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        setState({
          phase: 'error',
          message: `Failed to get agent token: ${errorData.detail || response.statusText}`,
        });
        return;
      }

      const { access_token } = await response.json();

      setState({ phase: 'exchanging', message: 'Redirecting to your local agent...' });
      window.location.href = `${callbackUrl}?token=${encodeURIComponent(access_token)}`;
    } catch (error) {
      console.error('Agent auth bridge error:', error);
      setState({ phase: 'error', message: 'Failed to complete authentication. Please try again.' });
    }
  }, [callbackUrl, getToken]);

  // Loading state
  if (!isLoaded) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[var(--background)]">
        <div className="w-5 h-5 border-2 border-[var(--primary)] border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  // No callback URL
  if (!callbackUrl) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[var(--background)] p-5">
        <div className="bg-[var(--card)] rounded-2xl p-10 max-w-md w-full shadow-lg border border-[var(--border)] text-center">
          <div className="text-5xl mb-4">📓</div>
          <h1 className="text-2xl font-semibold text-[var(--foreground)] mb-3">rMirror Agent</h1>
          <p className="text-[var(--muted-foreground)]">
            This page is used by the rMirror Agent for authentication.
            Please open it from your agent application.
          </p>
        </div>
      </div>
    );
  }

  // Invalid callback URL
  if (!validateCallbackUrl(callbackUrl)) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[var(--background)] p-5">
        <div className="bg-[var(--card)] rounded-2xl p-10 max-w-md w-full shadow-lg border border-[var(--border)] text-center">
          <div className="text-5xl mb-4">⚠️</div>
          <h1 className="text-2xl font-semibold text-[var(--foreground)] mb-3">Invalid Request</h1>
          <p className="text-[var(--muted-foreground)]">
            The callback URL must point to localhost. This page can only authenticate
            with a locally running rMirror Agent.
          </p>
        </div>
      </div>
    );
  }

  // Not signed in — show Clerk SignIn
  if (!isSignedIn) {
    const signInUrl = `/agent?callback=${encodeURIComponent(callbackUrl)}`;
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-[var(--background)] p-5 gap-6">
        <div className="text-center">
          <div className="text-5xl mb-3">📓</div>
          <h1 className="text-2xl font-semibold text-[var(--foreground)] mb-1">rMirror Agent</h1>
          <p className="text-[var(--muted-foreground)]">Sign in to connect your agent</p>
        </div>
        <SignIn
          forceRedirectUrl={signInUrl}
          signUpForceRedirectUrl={signInUrl}
          signUpUrl="/sign-up"
        />
      </div>
    );
  }

  // Signed in — show confirm / exchanging / error states
  return (
    <div className="min-h-screen flex items-center justify-center bg-[var(--background)] p-5">
      <div className="bg-[var(--card)] rounded-2xl p-10 max-w-md w-full shadow-lg border border-[var(--border)]">
        <div className="text-center mb-8">
          <div className="text-5xl mb-3">📓</div>
          <h1 className="text-2xl font-semibold text-[var(--foreground)] mb-1">rMirror Agent</h1>
          <p className="text-[var(--muted-foreground)]">Connect your agent to rMirror Cloud</p>
        </div>

        {state.phase === 'confirm' && (
          <>
            <div className="bg-[var(--background)] rounded-xl p-5 mb-6 text-center">
              <p className="text-sm text-[var(--muted-foreground)] mb-1">Continue as</p>
              <p className="font-semibold text-[var(--foreground)]">{displayName}</p>
              {email && <p className="text-sm text-[var(--muted-foreground)]">{email}</p>}
            </div>

            <button
              onClick={exchangeAndRedirect}
              className="w-full py-3 px-4 rounded-lg font-medium text-white bg-[var(--primary)] hover:brightness-90 transition-all mb-3"
            >
              Continue
            </button>
            <button
              onClick={() => signOut()}
              className="w-full py-3 px-4 rounded-lg font-medium text-[var(--primary)] bg-transparent border border-[var(--primary)] hover:bg-[var(--terracotta-light)] transition-all"
            >
              Use Different Account
            </button>
          </>
        )}

        {state.phase === 'exchanging' && (
          <div className="text-center">
            <div className="flex items-center justify-center gap-3 bg-[var(--background)] rounded-xl p-5">
              <div className="w-4 h-4 border-2 border-[var(--primary)] border-t-transparent rounded-full animate-spin" />
              <p className="text-[var(--muted-foreground)]">{state.message}</p>
            </div>
          </div>
        )}

        {state.phase === 'error' && (
          <>
            <div className="bg-[var(--destructive-bg)] border border-[var(--destructive-border-solid)] rounded-xl p-5 mb-6 text-center">
              <p className="text-[var(--destructive)]">{state.message}</p>
            </div>
            <button
              onClick={() => { setState({ phase: 'confirm' }); }}
              className="w-full py-3 px-4 rounded-lg font-medium text-white bg-[var(--primary)] hover:brightness-90 transition-all"
            >
              Try Again
            </button>
          </>
        )}
      </div>
    </div>
  );
}

export default function AgentAuthBridgePage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen flex items-center justify-center bg-[var(--background)]">
        <div className="w-5 h-5 border-2 border-[var(--primary)] border-t-transparent rounded-full animate-spin" />
      </div>
    }>
      <AgentAuthBridgeInner />
    </Suspense>
  );
}
