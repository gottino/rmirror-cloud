import { renderHook, act, waitFor } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import type { NotebookPagesResponse, Page } from '../../lib/api';
import {
  mergePages,
  useLoadMoreSentinel,
  useNotebookPages,
  MAX_PAGE_WINDOW,
  type FetchPagesWindow,
} from '../../lib/useNotebookPages';

function makePage(pageNumber: number): Page {
  return {
    id: 1000 + pageNumber,
    notebook_id: 1,
    page_number: pageNumber,
    ocr_status: 'completed',
    ocr_text: `text ${pageNumber}`,
    ocr_error: null,
    pdf_s3_key: null,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  };
}

/** Fake backend: `total` pages served newest first, like order=desc. */
function fakeBackend(total: number) {
  const all = Array.from({ length: total }, (_, i) => makePage(total - i));
  const fetchWindow = vi.fn<Parameters<FetchPagesWindow>, ReturnType<FetchPagesWindow>>(
    async (offset, limit): Promise<NotebookPagesResponse> => {
      const items = all.slice(offset, offset + limit);
      return { items, total, offset, limit, has_more: offset + items.length < total };
    }
  );
  return fetchWindow;
}

describe('mergePages', () => {
  it('appends new pages and skips ones already loaded', () => {
    const a = [makePage(3), makePage(2)];
    const merged = mergePages(a, [makePage(2), makePage(1)]);
    expect(merged.map((p) => p.page_number)).toEqual([3, 2, 1]);
  });

  it('returns the same array when nothing is new', () => {
    const a = [makePage(1)];
    expect(mergePages(a, [makePage(1)])).toBe(a);
  });
});

describe('useNotebookPages', () => {
  it('fetches only the first window initially for a 300-page notebook', async () => {
    const fetchWindow = fakeBackend(300);
    const { result } = renderHook(() => useNotebookPages(1, fetchWindow, 50));

    await waitFor(() => expect(result.current.pages).toHaveLength(50));
    expect(fetchWindow).toHaveBeenCalledTimes(1);
    expect(fetchWindow).toHaveBeenCalledWith(0, 50);
    expect(result.current.total).toBe(300);
    expect(result.current.hasMore).toBe(true);
    expect(result.current.pages[0].page_number).toBe(300);
  });

  it('does nothing while the key is null', async () => {
    const fetchWindow = fakeBackend(10);
    const { result } = renderHook(() => useNotebookPages(null, fetchWindow));
    await act(async () => {
      expect(await result.current.loadMore()).toBe(false);
    });
    expect(fetchWindow).not.toHaveBeenCalled();
    expect(result.current.hasMore).toBe(false);
  });

  it('loads subsequent windows from the right offset and stops at the end', async () => {
    const fetchWindow = fakeBackend(120);
    const { result } = renderHook(() => useNotebookPages(1, fetchWindow, 50));
    await waitFor(() => expect(result.current.pages).toHaveLength(50));

    await act(async () => {
      await result.current.loadMore();
    });
    expect(fetchWindow).toHaveBeenLastCalledWith(50, 50);
    expect(result.current.pages).toHaveLength(100);

    await act(async () => {
      await result.current.loadMore();
    });
    expect(result.current.pages).toHaveLength(120);
    expect(result.current.hasMore).toBe(false);

    await act(async () => {
      expect(await result.current.loadMore()).toBe(false);
    });
    expect(fetchWindow).toHaveBeenCalledTimes(3);
  });

  it('shares one request between concurrent loadMore calls', async () => {
    const fetchWindow = fakeBackend(200);
    const { result } = renderHook(() => useNotebookPages(1, fetchWindow, 50));
    await waitFor(() => expect(result.current.pages).toHaveLength(50));

    await act(async () => {
      await Promise.all([result.current.loadMore(), result.current.loadMore()]);
    });
    expect(fetchWindow).toHaveBeenCalledTimes(2);
    expect(result.current.pages).toHaveLength(100);
  });

  it('loadUntil loads up to a page that is not loaded yet, in max-size windows', async () => {
    const fetchWindow = fakeBackend(300);
    const { result } = renderHook(() => useNotebookPages(1, fetchWindow, 50));
    await waitFor(() => expect(result.current.pages).toHaveLength(50));

    let found = false;
    await act(async () => {
      found = await result.current.loadUntil((p) => p.page_number === 120);
    });
    expect(found).toBe(true);
    expect(result.current.pages.some((p) => p.page_number === 120)).toBe(true);
    // 300..251 initially, then 250..151 and 150..51 in windows of 100
    expect(fetchWindow.mock.calls).toEqual([
      [0, 50],
      [50, MAX_PAGE_WINDOW],
      [150, MAX_PAGE_WINDOW],
    ]);
  });

  it('loadUntil resolves false for a page that does not exist', async () => {
    const fetchWindow = fakeBackend(60);
    const { result } = renderHook(() => useNotebookPages(1, fetchWindow, 50));

    let found = true;
    await act(async () => {
      found = await result.current.loadUntil((p) => p.page_number === 999);
    });
    expect(found).toBe(false);
    expect(result.current.pages).toHaveLength(60);
    expect(result.current.hasMore).toBe(false);
  });

  it('keeps loaded pages and reports an error when a window fails', async () => {
    const backend = fakeBackend(100);
    const fetchWindow = vi.fn<Parameters<FetchPagesWindow>, ReturnType<FetchPagesWindow>>(
      async (offset, limit) => {
        if (offset > 0) throw new Error('boom');
        return backend(offset, limit);
      }
    );
    const { result } = renderHook(() => useNotebookPages(1, fetchWindow, 50));
    await waitFor(() => expect(result.current.pages).toHaveLength(50));

    await act(async () => {
      expect(await result.current.loadMore()).toBe(false);
    });
    expect(result.current.error).toBe('boom');
    expect(result.current.pages).toHaveLength(50);
    expect(result.current.hasMore).toBe(true);
  });

  it('resets when the key changes and ignores the old notebook\'s late response', async () => {
    let resolveOld: (v: NotebookPagesResponse) => void = () => {};
    const slow = new Promise<NotebookPagesResponse>((r) => {
      resolveOld = r;
    });
    const second = fakeBackend(5);
    let calls = 0;
    const fetchWindow = vi.fn<Parameters<FetchPagesWindow>, ReturnType<FetchPagesWindow>>(
      (offset, limit) => (++calls === 1 ? slow : second(offset, limit))
    );

    const { result, rerender } = renderHook(({ id }) => useNotebookPages(id, fetchWindow, 50), {
      initialProps: { id: 1 },
    });
    rerender({ id: 2 });
    await waitFor(() => expect(result.current.pages).toHaveLength(5));

    await act(async () => {
      resolveOld({ items: [makePage(77)], total: 1, offset: 0, limit: 50, has_more: false });
      await slow;
    });
    expect(result.current.pages.map((p) => p.page_number)).toEqual([5, 4, 3, 2, 1]);
  });

  it('does not reset when only the fetch function identity changes', async () => {
    const fetchWindow = fakeBackend(80);
    const { result, rerender } = renderHook(
      ({ fn }) => useNotebookPages(1, fn, 50),
      { initialProps: { fn: fetchWindow as FetchPagesWindow } }
    );
    await waitFor(() => expect(result.current.pages).toHaveLength(50));

    const replacement = vi.fn(fetchWindow);
    rerender({ fn: replacement });
    await act(async () => {
      await result.current.loadMore();
    });
    expect(result.current.pages).toHaveLength(80);
    expect(replacement).toHaveBeenCalledWith(50, 50);
  });
});

describe('useLoadMoreSentinel', () => {
  it('calls back when the sentinel intersects and re-arms on watchKey change', () => {
    const instances: { cb: IntersectionObserverCallback; disconnect: ReturnType<typeof vi.fn> }[] = [];
    const original = globalThis.IntersectionObserver;
    globalThis.IntersectionObserver = vi.fn((cb: IntersectionObserverCallback) => {
      const inst = { cb, observe: vi.fn(), disconnect: vi.fn(), unobserve: vi.fn() };
      instances.push(inst);
      return inst;
    }) as unknown as typeof IntersectionObserver;

    try {
      const onVisible = vi.fn();
      const { result, rerender } = renderHook(
        ({ key, enabled }) => useLoadMoreSentinel(onVisible, { enabled, watchKey: key }),
        { initialProps: { key: 0, enabled: true } }
      );
      act(() => result.current(document.createElement('div')));
      expect(instances).toHaveLength(1);

      instances[0].cb([{ isIntersecting: true } as IntersectionObserverEntry], {} as IntersectionObserver);
      expect(onVisible).toHaveBeenCalledTimes(1);
      instances[0].cb([{ isIntersecting: false } as IntersectionObserverEntry], {} as IntersectionObserver);
      expect(onVisible).toHaveBeenCalledTimes(1);

      rerender({ key: 1, enabled: true });
      expect(instances[0].disconnect).toHaveBeenCalled();
      expect(instances).toHaveLength(2);

      rerender({ key: 1, enabled: false });
      expect(instances[1].disconnect).toHaveBeenCalled();
      expect(instances).toHaveLength(2);
    } finally {
      globalThis.IntersectionObserver = original;
    }
  });
});

describe('useNotebookPages key switch', () => {
  it('reports loading, not an empty finished list, on the render where the key appears', () => {
    const fetchWindow = vi.fn<Parameters<FetchPagesWindow>, ReturnType<FetchPagesWindow>>(
      () => new Promise(() => {})
    );
    const seen: { loading: boolean; hasMore: boolean }[] = [];
    const { rerender } = renderHook(({ id }) => {
      const r = useNotebookPages(id, fetchWindow);
      seen.push({ loading: r.loading, hasMore: r.hasMore });
      return r;
    }, { initialProps: { id: null as number | null } });
    seen.length = 0;
    rerender({ id: 3 });
    expect(seen.length).toBeGreaterThan(0);
    for (const s of seen) {
      expect(s.loading || s.hasMore).toBe(true);
    }
  });
});
