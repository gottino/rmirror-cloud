'use client';

import { useCallback, useEffect, useRef, useState, type Dispatch, type SetStateAction } from 'react';

export interface ApiQuery<T> {
  data: T | null;
  error: Error | null;
  /** True while the first request for the current key is in flight. */
  loading: boolean;
  /** Refetch in the background, keeping the current data until it arrives. */
  reload: () => Promise<void>;
  /** Replace the data locally (optimistic updates, mutation responses). */
  setData: Dispatch<SetStateAction<T | null>>;
}

function isAbort(err: unknown): boolean {
  return err instanceof Error && err.name === 'AbortError';
}

/**
 * Minimal read hook: runs `fetcher` whenever `key` changes (null disables it),
 * aborts the request in flight on key change, reload and unmount, and ignores
 * results that arrive for a superseded request. `fetcher` may change identity
 * freely; only `key` triggers a new request.
 */
export function useApiQuery<T>(
  key: string | null,
  fetcher: (signal: AbortSignal) => Promise<T>
): ApiQuery<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [loading, setLoading] = useState(key !== null);
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;
  const controllerRef = useRef<AbortController | null>(null);
  const keyRef = useRef(key);
  keyRef.current = key;

  const run = useCallback(async () => {
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    setError(null);
    try {
      const result = await fetcherRef.current(controller.signal);
      if (!controller.signal.aborted) setData(result);
    } catch (err) {
      if (controller.signal.aborted || isAbort(err)) return;
      console.error('API request failed:', keyRef.current, err);
      setError(err instanceof Error ? err : new Error(String(err)));
    } finally {
      if (controllerRef.current === controller) {
        controllerRef.current = null;
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    setData(null);
    if (key === null) {
      controllerRef.current?.abort();
      controllerRef.current = null;
      setError(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    void run();
    return () => {
      controllerRef.current?.abort();
      controllerRef.current = null;
    };
  }, [key, run]);

  const reload = useCallback(async () => {
    if (keyRef.current === null) return;
    await run();
  }, [run]);

  return { data, error, loading, reload, setData };
}
