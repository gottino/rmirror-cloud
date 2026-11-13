import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { useApiQuery } from '../../lib/useApiQuery';

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (err: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

describe('useApiQuery', () => {
  beforeEach(() => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('loads data for a key', async () => {
    const fetcher = vi.fn().mockResolvedValue({ n: 1 });
    const { result } = renderHook(() => useApiQuery('k', fetcher));

    expect(result.current.loading).toBe(true);
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.data).toEqual({ n: 1 });
    expect(result.current.error).toBeNull();
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(fetcher.mock.calls[0][0]).toBeInstanceOf(AbortSignal);
  });

  it('does nothing while the key is null', () => {
    const fetcher = vi.fn();
    const { result } = renderHook(() => useApiQuery(null, fetcher));

    expect(result.current).toMatchObject({ data: null, error: null, loading: false });
    expect(fetcher).not.toHaveBeenCalled();
  });

  it('exposes errors and stops loading', async () => {
    const fetcher = vi.fn().mockRejectedValue(new Error('nope'));
    const { result } = renderHook(() => useApiQuery('k', fetcher));

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error?.message).toBe('nope');
    expect(result.current.data).toBeNull();
  });

  it('does not refetch when only the fetcher identity changes', async () => {
    const { result, rerender } = renderHook(
      ({ value }) => useApiQuery('k', async () => value),
      { initialProps: { value: 1 } }
    );
    await waitFor(() => expect(result.current.data).toBe(1));

    rerender({ value: 2 });
    expect(result.current.data).toBe(1);

    // reload uses the latest fetcher
    await act(() => result.current.reload());
    expect(result.current.data).toBe(2);
  });

  it('refetches on key change and aborts the superseded request', async () => {
    const first = deferred<string>();
    const signals: AbortSignal[] = [];
    const fetcher = vi.fn((signal: AbortSignal) => {
      signals.push(signal);
      return signals.length === 1 ? first.promise : Promise.resolve('second');
    });
    const { result, rerender } = renderHook(({ k }) => useApiQuery(k, fetcher), {
      initialProps: { k: 'a' },
    });

    rerender({ k: 'b' });
    await waitFor(() => expect(result.current.data).toBe('second'));
    expect(signals[0].aborted).toBe(true);

    // the stale response arriving late is ignored
    await act(async () => first.resolve('first'));
    expect(result.current.data).toBe('second');
  });

  it('aborts the request in flight on unmount', () => {
    let signal: AbortSignal | undefined;
    const { unmount } = renderHook(() =>
      useApiQuery('k', (s) => {
        signal = s;
        return new Promise(() => {});
      })
    );

    unmount();
    expect(signal?.aborted).toBe(true);
  });

  it('reload keeps the current data while refetching', async () => {
    const next = deferred<number>();
    const fetcher = vi.fn().mockResolvedValueOnce(1).mockReturnValueOnce(next.promise);
    const { result } = renderHook(() => useApiQuery('k', fetcher));
    await waitFor(() => expect(result.current.data).toBe(1));

    let reloading!: Promise<void>;
    act(() => {
      reloading = result.current.reload();
    });
    expect(result.current.data).toBe(1);
    expect(result.current.loading).toBe(false);

    await act(async () => {
      next.resolve(2);
      await reloading;
    });
    expect(result.current.data).toBe(2);
  });

  it('setData replaces the data locally', async () => {
    const { result } = renderHook(() => useApiQuery('k', async () => ({ dismissed: false })));
    await waitFor(() => expect(result.current.data).toEqual({ dismissed: false }));

    act(() => result.current.setData((prev) => prev && { ...prev, dismissed: true }));
    expect(result.current.data).toEqual({ dismissed: true });
  });
});
