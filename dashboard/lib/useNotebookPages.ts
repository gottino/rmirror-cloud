'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import type { NotebookPagesResponse, Page } from './api';

/** Pages requested per window when scrolling / pressing "Load more". */
export const PAGE_WINDOW_SIZE = 50;
/** Backend cap for one window; used when jumping to a page that is far away. */
export const MAX_PAGE_WINDOW = 100;

export type FetchPagesWindow = (offset: number, limit: number) => Promise<NotebookPagesResponse>;

export interface NotebookPagesState {
  pages: Page[];
  /** Total pages reported by the server, or null before the first window arrives. */
  total: number | null;
  hasMore: boolean;
  /** Rows consumed from the server so far (next window starts here). */
  offset: number;
  loading: boolean;
  error: string | null;
}

const initialState = (enabled: boolean): NotebookPagesState => ({
  pages: [],
  total: null,
  hasMore: enabled,
  offset: 0,
  loading: false,
  error: null,
});

/**
 * Append a window of pages, skipping any page already loaded (a page added
 * while scrolling can shift offsets and repeat a page across windows).
 */
export function mergePages(existing: Page[], incoming: Page[]): Page[] {
  const seen = new Set(existing.map((p) => p.id));
  const added = incoming.filter((p) => !seen.has(p.id));
  return added.length > 0 ? [...existing, ...added] : existing;
}

/**
 * Incrementally load a notebook's pages.
 *
 * `key` identifies the notebook; null disables loading. When the key changes
 * the loaded pages are dropped and the first window is fetched. `fetchWindow`
 * may change identity freely (e.g. when the auth token getter changes) without
 * resetting what is loaded.
 */
export function useNotebookPages(
  key: number | string | null,
  fetchWindow: FetchPagesWindow,
  pageSize: number = PAGE_WINDOW_SIZE
) {
  const [state, setState] = useState<NotebookPagesState>(() => initialState(key !== null));
  const stateRef = useRef(state);
  const fetchRef = useRef(fetchWindow);
  const generation = useRef(0);
  const inFlight = useRef<Promise<boolean> | null>(null);

  useEffect(() => {
    fetchRef.current = fetchWindow;
  }, [fetchWindow]);

  const commit = useCallback((next: NotebookPagesState) => {
    stateRef.current = next;
    setState(next);
  }, []);

  /** Fetch the next window. Resolves true when a window was loaded. */
  const loadMore = useCallback(
    (limit?: number): Promise<boolean> => {
      if (inFlight.current) return inFlight.current;
      const current = stateRef.current;
      if (key === null || !current.hasMore) return Promise.resolve(false);

      const gen = generation.current;
      const size = Math.max(1, Math.min(limit ?? pageSize, MAX_PAGE_WINDOW));
      commit({ ...current, loading: true, error: null });

      const request: Promise<boolean> = fetchRef
        .current(current.offset, size)
        .then((res) => {
          if (gen !== generation.current) return false;
          const prev = stateRef.current;
          commit({
            pages: mergePages(prev.pages, res.items),
            total: res.total,
            // An empty window means the list shrank under us; stop rather than loop.
            hasMore: res.has_more && res.items.length > 0,
            offset: prev.offset + res.items.length,
            loading: false,
            error: null,
          });
          return true;
        })
        .catch((err: unknown) => {
          if (gen !== generation.current) return false;
          commit({
            ...stateRef.current,
            loading: false,
            error: err instanceof Error ? err.message : 'Failed to load pages',
          });
          return false;
        })
        .finally(() => {
          if (inFlight.current === request) inFlight.current = null;
        });

      inFlight.current = request;
      return request;
    },
    [key, pageSize, commit]
  );

  /**
   * Load windows until a page matching `predicate` is loaded or the notebook
   * has no more pages. Resolves true when the page is loaded.
   */
  const loadUntil = useCallback(
    async (predicate: (page: Page) => boolean): Promise<boolean> => {
      const gen = generation.current;
      for (;;) {
        if (stateRef.current.pages.some(predicate)) return true;
        if (gen !== generation.current || !stateRef.current.hasMore) return false;
        const ok = await loadMore(MAX_PAGE_WINDOW);
        // Nothing loaded (error, end of list, or notebook changed): stop here.
        if (!ok) return gen === generation.current && stateRef.current.pages.some(predicate);
      }
    },
    [loadMore]
  );

  // Reset and load the first window whenever the notebook changes.
  const [loadedKey, setLoadedKey] = useState(key);
  useEffect(() => {
    generation.current += 1;
    inFlight.current = null;
    commit(initialState(key !== null));
    setLoadedKey(key);
    if (key !== null) {
      void loadMore();
    }
  }, [key, loadMore, commit]);

  // Until the reset effect has run for a new key, report the pending state
  // instead of the previous notebook's pages (avoids a flash of stale/empty UI).
  const visible: NotebookPagesState =
    loadedKey === key ? state : { ...initialState(key !== null), loading: key !== null };

  return { ...visible, loadMore, loadUntil };
}

/**
 * Call `onVisible` when the returned sentinel element scrolls into view
 * (within `rootMargin` of `root`). The observer is re-armed whenever
 * `watchKey` changes so a sentinel that stays visible after a load triggers
 * the next load too.
 */
export function useLoadMoreSentinel(
  onVisible: () => void,
  options: {
    enabled: boolean;
    root?: Element | null;
    rootMargin?: string;
    watchKey?: unknown;
  }
) {
  const { enabled, root = null, rootMargin = '600px', watchKey } = options;
  const [element, setElement] = useState<Element | null>(null);
  const callbackRef = useRef(onVisible);

  useEffect(() => {
    callbackRef.current = onVisible;
  }, [onVisible]);

  useEffect(() => {
    if (!enabled || !element || typeof IntersectionObserver === 'undefined') return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) callbackRef.current();
      },
      { root, rootMargin }
    );
    observer.observe(element);
    return () => observer.disconnect();
  }, [enabled, element, root, rootMargin, watchKey]);

  return setElement;
}
