import { render, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import React from 'react';

const auth = vi.hoisted(() => ({
  isSignedIn: true as boolean | undefined,
  getToken: async () => 'token',
}));

vi.mock('@clerk/nextjs', () => ({
  useAuth: () => auth,
}));

vi.mock('@/lib/api', () => ({
  getQuotaStatus: vi.fn().mockResolvedValue({ used: 1, limit: 30 }),
}));

import { getQuotaStatus } from '@/lib/api';
import { QuotaProvider, useQuota } from '../../lib/quota-context';
import { QUOTA_POLL_INTERVAL_MS } from '../../lib/constants';

const mockGetQuota = vi.mocked(getQuotaStatus);

function setHidden(hidden: boolean) {
  Object.defineProperty(document, 'hidden', { configurable: true, get: () => hidden });
}

function Probe() {
  const { loading } = useQuota();
  return <span data-testid="loading">{String(loading)}</span>;
}

async function flush() {
  await act(async () => {
    await Promise.resolve();
  });
}

describe('QuotaProvider', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    mockGetQuota.mockClear();
    auth.isSignedIn = true;
    setHidden(false);
  });

  afterEach(() => {
    vi.useRealTimers();
    setHidden(false);
  });

  it('fetches on mount and polls while visible', async () => {
    render(<QuotaProvider><Probe /></QuotaProvider>);
    await flush();
    expect(mockGetQuota).toHaveBeenCalledTimes(1);

    await act(async () => {
      vi.advanceTimersByTime(QUOTA_POLL_INTERVAL_MS);
    });
    expect(mockGetQuota).toHaveBeenCalledTimes(2);
  });

  it('does not fetch or poll without a signed-in user', async () => {
    auth.isSignedIn = false;
    const { getByTestId } = render(<QuotaProvider><Probe /></QuotaProvider>);
    await flush();
    await act(async () => {
      vi.advanceTimersByTime(QUOTA_POLL_INTERVAL_MS * 3);
    });
    expect(mockGetQuota).not.toHaveBeenCalled();
    expect(vi.getTimerCount()).toBe(0);
    expect(getByTestId('loading').textContent).toBe('false');
  });

  it('does not fetch while the tab is hidden and resumes when visible', async () => {
    setHidden(true);
    render(<QuotaProvider><Probe /></QuotaProvider>);
    await flush();
    await act(async () => {
      vi.advanceTimersByTime(QUOTA_POLL_INTERVAL_MS * 3);
    });
    expect(mockGetQuota).not.toHaveBeenCalled();

    setHidden(false);
    await act(async () => {
      document.dispatchEvent(new Event('visibilitychange'));
    });
    expect(mockGetQuota).toHaveBeenCalledTimes(1);

    await act(async () => {
      vi.advanceTimersByTime(QUOTA_POLL_INTERVAL_MS);
    });
    expect(mockGetQuota).toHaveBeenCalledTimes(2);
  });

  it('stops polling when the tab becomes hidden', async () => {
    render(<QuotaProvider><Probe /></QuotaProvider>);
    await flush();
    expect(mockGetQuota).toHaveBeenCalledTimes(1);

    setHidden(true);
    await act(async () => {
      document.dispatchEvent(new Event('visibilitychange'));
    });
    await act(async () => {
      vi.advanceTimersByTime(QUOTA_POLL_INTERVAL_MS * 3);
    });
    expect(mockGetQuota).toHaveBeenCalledTimes(1);
  });
});
