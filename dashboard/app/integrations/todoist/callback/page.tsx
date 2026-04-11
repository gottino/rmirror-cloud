'use client';

import { Suspense, useEffect, useState } from 'react';
import { useAuth } from '@clerk/nextjs';
import { useRouter, useSearchParams } from 'next/navigation';
import { todoistOAuthCallback } from '@/lib/api';
import { trackEvent } from '@/lib/analytics';

function TodoistCallbackContent() {
  const { getToken } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [status, setStatus] = useState<'loading' | 'success' | 'error'>('loading');
  const [error, setError] = useState<string | null>(null);

  // Development mode bypass
  const isDevelopmentMode = process.env.NEXT_PUBLIC_DEV_MODE === 'true';

  useEffect(() => {
    handleCallback();
  }, []);

  async function handleCallback() {
    try {
      const code = searchParams.get('code');
      const state = searchParams.get('state');

      if (!code || !state) {
        setError('Missing OAuth parameters');
        setStatus('error');
        return;
      }

      const token = isDevelopmentMode
        ? process.env.NEXT_PUBLIC_DEV_AUTH_TOKEN || localStorage.getItem('dev_auth_token') || ''
        : await getToken();
      if (!token) {
        router.push('/sign-in');
        return;
      }

      await todoistOAuthCallback(token, code, state);
      trackEvent({ name: 'integration_connected', data: { service: 'todoist' } });
      setStatus('success');

      // Redirect to project setup page after 2 seconds
      setTimeout(() => {
        router.push('/integrations/todoist/setup');
      }, 2000);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to complete OAuth');
      setStatus('error');
    }
  }

  return (
    <div
      className="flex items-center justify-center min-h-screen"
      style={{ backgroundColor: 'var(--soft-cream)' }}
    >
      <div
        className="rounded-lg shadow-lg p-8 max-w-md w-full"
        style={{ backgroundColor: 'white', border: '1px solid var(--border)' }}
      >
        {status === 'loading' && (
          <>
            <div className="flex justify-center mb-4">
              <div
                className="animate-spin rounded-full h-12 w-12 border-b-2"
                style={{ borderColor: 'var(--terracotta)' }}
              ></div>
            </div>
            <h2
              className="text-xl font-semibold text-center mb-2"
              style={{ color: 'var(--warm-charcoal)' }}
            >
              Connecting to Todoist...
            </h2>
            <p className="text-center" style={{ color: 'var(--warm-gray)' }}>
              Please wait while we complete the authentication
            </p>
          </>
        )}

        {status === 'success' && (
          <>
            <div className="flex justify-center mb-4">
              <div
                className="rounded-full p-3"
                style={{ backgroundColor: 'var(--sage-green-light, #e6f4ec)' }}
              >
                <svg
                  className="w-12 h-12"
                  style={{ color: 'var(--sage-green)' }}
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M5 13l4 4L19 7"
                  />
                </svg>
              </div>
            </div>
            <h2
              className="text-xl font-semibold text-center mb-2"
              style={{ color: 'var(--sage-green)' }}
            >
              Successfully Connected!
            </h2>
            <p className="text-center" style={{ color: 'var(--warm-gray)' }}>
              Redirecting to project setup...
            </p>
          </>
        )}

        {status === 'error' && (
          <>
            <div className="flex justify-center mb-4">
              <div
                className="rounded-full p-3"
                style={{ backgroundColor: 'var(--destructive-bg, #fef2f2)' }}
              >
                <svg
                  className="w-12 h-12"
                  style={{ color: 'var(--destructive)' }}
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M6 18L18 6M6 6l12 12"
                  />
                </svg>
              </div>
            </div>
            <h2
              className="text-xl font-semibold text-center mb-2"
              style={{ color: 'var(--destructive)' }}
            >
              Connection Failed
            </h2>
            <p className="text-center mb-4" style={{ color: 'var(--warm-gray)' }}>
              {error}
            </p>
            <button
              onClick={() => router.push('/integrations')}
              className="w-full px-4 py-2 rounded-md font-medium transition-colors"
              style={{ backgroundColor: 'var(--warm-charcoal)', color: 'white' }}
            >
              Back to Integrations
            </button>
          </>
        )}
      </div>
    </div>
  );
}

export default function TodoistCallbackPage() {
  return (
    <Suspense
      fallback={
        <div
          className="flex items-center justify-center min-h-screen"
          style={{ backgroundColor: 'var(--soft-cream)' }}
        >
          <div
            className="rounded-lg shadow-lg p-8 max-w-md w-full"
            style={{ backgroundColor: 'white', border: '1px solid var(--border)' }}
          >
            <div className="flex justify-center mb-4">
              <div
                className="animate-spin rounded-full h-12 w-12 border-b-2"
                style={{ borderColor: 'var(--terracotta)' }}
              ></div>
            </div>
            <h2
              className="text-xl font-semibold text-center mb-2"
              style={{ color: 'var(--warm-charcoal)' }}
            >
              Loading...
            </h2>
          </div>
        </div>
      }
    >
      <TodoistCallbackContent />
    </Suspense>
  );
}
