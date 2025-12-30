'use client';

import { Suspense, useEffect, useState } from 'react';
import { useAuth } from '@clerk/nextjs';
import { useRouter, useSearchParams } from 'next/navigation';
import { notionOAuthCallback } from '@/lib/api';

function NotionCallbackContent() {
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

      await notionOAuthCallback(token, code, state);
      setStatus('success');

      // Redirect to setup page after 2 seconds
      setTimeout(() => {
        router.push('/integrations/notion/setup?type=notebooks');
      }, 2000);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to complete OAuth');
      setStatus('error');
    }
  }

  return (
    <div className="flex items-center justify-center min-h-screen bg-gray-50">
      <div className="bg-white rounded-lg shadow-lg p-8 max-w-md w-full">
        {status === 'loading' && (
          <>
            <div className="flex justify-center mb-4">
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-black"></div>
            </div>
            <h2 className="text-xl font-semibold text-center mb-2">
              Connecting to Notion...
            </h2>
            <p className="text-gray-600 text-center">
              Please wait while we complete the authentication
            </p>
          </>
        )}

        {status === 'success' && (
          <>
            <div className="flex justify-center mb-4">
              <div className="rounded-full bg-green-100 p-3">
                <svg
                  className="w-12 h-12 text-green-600"
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
            <h2 className="text-xl font-semibold text-center mb-2 text-green-600">
              Successfully Connected!
            </h2>
            <p className="text-gray-600 text-center">
              Redirecting to database setup...
            </p>
          </>
        )}

        {status === 'error' && (
          <>
            <div className="flex justify-center mb-4">
              <div className="rounded-full bg-red-100 p-3">
                <svg
                  className="w-12 h-12 text-red-600"
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
            <h2 className="text-xl font-semibold text-center mb-2 text-red-600">
              Connection Failed
            </h2>
            <p className="text-gray-600 text-center mb-4">{error}</p>
            <button
              onClick={() => router.push('/integrations')}
              className="w-full px-4 py-2 bg-black hover:bg-gray-800 text-white rounded-md font-medium"
            >
              Back to Integrations
            </button>
          </>
        )}
      </div>
    </div>
  );
}

export default function NotionCallbackPage() {
  return (
    <Suspense
      fallback={
        <div className="flex items-center justify-center min-h-screen bg-gray-50">
          <div className="bg-white rounded-lg shadow-lg p-8 max-w-md w-full">
            <div className="flex justify-center mb-4">
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-black"></div>
            </div>
            <h2 className="text-xl font-semibold text-center mb-2">
              Loading...
            </h2>
          </div>
        </div>
      }
    >
      <NotionCallbackContent />
    </Suspense>
  );
}
