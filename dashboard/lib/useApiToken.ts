'use client';

import { useAuth } from '@clerk/nextjs';
import { useCallback } from 'react';

/**
 * Local development auth bypass: `NEXT_PUBLIC_DEV_MODE=true` in a
 * non-production build. Always false in a production build.
 */
export function isDevAuthMode(): boolean {
  return process.env.NODE_ENV !== 'production' && process.env.NEXT_PUBLIC_DEV_MODE === 'true';
}

/**
 * Returns a stable `getToken()` for backend calls: a fresh Clerk session token,
 * or in local dev auth mode the JWT stored in localStorage (`dev_auth_token`).
 */
export function useApiToken(): () => Promise<string | null> {
  const { getToken } = useAuth();

  return useCallback(async () => {
    // Written out (not via isDevAuthMode) so the bundler folds the condition
    // and drops this branch from production builds.
    if (process.env.NODE_ENV !== 'production' && process.env.NEXT_PUBLIC_DEV_MODE === 'true') {
      return window.localStorage.getItem('dev_auth_token') || '';
    }
    return getToken();
  }, [getToken]);
}
