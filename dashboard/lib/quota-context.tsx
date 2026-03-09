'use client';

import { createContext, useContext, useEffect, useState, useCallback, useRef, type ReactNode } from 'react';
import { useAuth } from '@clerk/nextjs';
import { getQuotaStatus, type QuotaStatus } from '@/lib/api';
import { QUOTA_POLL_INTERVAL_MS } from '@/lib/constants';

interface QuotaContextValue {
  quota: QuotaStatus | null;
  loading: boolean;
  error: string | null;
  refetch: () => Promise<void>;
}

const QuotaContext = createContext<QuotaContextValue>({
  quota: null,
  loading: true,
  error: null,
  refetch: async () => {},
});

export function useQuota() {
  return useContext(QuotaContext);
}

interface QuotaProviderProps {
  children: ReactNode;
}

export function QuotaProvider({ children }: QuotaProviderProps) {
  const { getToken, isSignedIn } = useAuth();
  const [quota, setQuota] = useState<QuotaStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval>>();

  const isDevelopmentMode = process.env.NEXT_PUBLIC_DEV_MODE === 'true';
  const effectiveIsSignedIn = isDevelopmentMode || isSignedIn;

  const fetchQuota = useCallback(async () => {
    if (!effectiveIsSignedIn) {
      setLoading(false);
      return;
    }

    try {
      setError(null);
      const token = isDevelopmentMode
        ? process.env.NEXT_PUBLIC_DEV_AUTH_TOKEN || localStorage.getItem('dev_auth_token') || ''
        : await getToken();

      if (!token) {
        setLoading(false);
        return;
      }

      const data = await getQuotaStatus(token);
      setQuota(data);
    } catch (err) {
      console.error('Error fetching quota:', err);
      setError(err instanceof Error ? err.message : 'Failed to fetch quota');
    } finally {
      setLoading(false);
    }
  }, [effectiveIsSignedIn, isDevelopmentMode, getToken]);

  useEffect(() => {
    fetchQuota();
    intervalRef.current = setInterval(fetchQuota, QUOTA_POLL_INTERVAL_MS);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [fetchQuota]);

  return (
    <QuotaContext.Provider value={{ quota, loading, error, refetch: fetchQuota }}>
      {children}
    </QuotaContext.Provider>
  );
}
