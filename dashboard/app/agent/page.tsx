'use client';

import { useAuth, useUser, SignIn, useClerk } from '@clerk/nextjs';
import { useSearchParams } from 'next/navigation';
import { useState, useCallback, Suspense } from 'react';
import Image from 'next/image';
import { validateCallbackUrl, buildAgentRedirectUrl } from '@/lib/agent-callback';
import { ApiError, exchangeAgentToken } from '@/lib/api';

const SIGN_IN_AGAIN = 'Open rMirror from your menu bar and choose Sign In again.';

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
      setState({ phase: 'error', message: `This sign-in link didn't come from rMirror on your Mac. ${SIGN_IN_AGAIN}` });
      return;
    }

    try {
      setState({ phase: 'exchanging', message: 'Connecting your Mac…' });

      const clerkToken = await getToken();
      if (!clerkToken) {
        setState({ phase: 'error', message: "We couldn't confirm your sign-in. Please try again." });
        return;
      }

      let access_token: string;
      try {
        ({ access_token } = await exchangeAgentToken(clerkToken));
      } catch (err) {
        if (!(err instanceof ApiError)) throw err;
        const detail = typeof err.detail === 'string' && err.detail ? err.detail : err.statusText;
        console.error('Agent token exchange failed:', detail);
        setState({ phase: 'error', message: `Your Mac couldn't be connected. ${SIGN_IN_AGAIN}` });
        return;
      }

      setState({ phase: 'exchanging', message: 'Returning to rMirror on your Mac…' });
      const redirectUrl = buildAgentRedirectUrl(callbackUrl, access_token);
      if (!redirectUrl) {
        setState({ phase: 'error', message: `This sign-in link didn't come from rMirror on your Mac. ${SIGN_IN_AGAIN}` });
        return;
      }
      window.location.assign(redirectUrl);
    } catch (error) {
      console.error('Agent auth bridge error:', error);
      setState({ phase: 'error', message: `Something went wrong while connecting your Mac. ${SIGN_IN_AGAIN}` });
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
          <Image src="/rm-icon.png" alt="rMirror" width={56} height={56} className="mx-auto mb-4" />
          <h1 className="text-2xl font-semibold text-[var(--foreground)] mb-3">rMirror for Mac</h1>
          <p className="text-[var(--muted-foreground)]">
            This page connects rMirror on your Mac to your account.
            Open rMirror from your menu bar and choose Sign In.
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
          <h1 className="text-2xl font-semibold text-[var(--foreground)] mb-3">This link can&apos;t be used</h1>
          <p className="text-[var(--muted-foreground)]">
            This page only works with a sign-in link from rMirror on your Mac.
            Open rMirror from your menu bar and choose Sign In again.
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
          <Image src="/rm-icon.png" alt="rMirror" width={56} height={56} className="mx-auto mb-3" />
          <h1 className="text-2xl font-semibold text-[var(--foreground)] mb-1">rMirror for Mac</h1>
          <p className="text-[var(--muted-foreground)]">Sign in to connect your Mac</p>
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
          <Image src="/rm-icon.png" alt="rMirror" width={56} height={56} className="mx-auto mb-3" />
          <h1 className="text-2xl font-semibold text-[var(--foreground)] mb-1">rMirror for Mac</h1>
          <p className="text-[var(--muted-foreground)]">Connect rMirror on your Mac to your account</p>
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
              onClick={() => signOut({ redirectUrl: `/agent?callback=${encodeURIComponent(callbackUrl)}` })}
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
