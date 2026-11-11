import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook } from '@testing-library/react';

const clerkGetToken = vi.fn();
vi.mock('@clerk/nextjs', () => ({
  useAuth: () => ({ getToken: clerkGetToken, isSignedIn: true }),
}));

import { isDevAuthMode, useApiToken } from '../../lib/useApiToken';

describe('useApiToken', () => {
  beforeEach(() => {
    clerkGetToken.mockReset().mockResolvedValue('clerk-token');
    window.localStorage.setItem('dev_auth_token', 'dev-token');
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    window.localStorage.clear();
  });

  it('returns the Clerk token when dev mode is off', async () => {
    vi.stubEnv('NEXT_PUBLIC_DEV_MODE', '');
    const { result } = renderHook(() => useApiToken());

    expect(await result.current()).toBe('clerk-token');
    expect(isDevAuthMode()).toBe(false);
  });

  it('returns the localStorage dev token in a non-production build with dev mode on', async () => {
    vi.stubEnv('NODE_ENV', 'development');
    vi.stubEnv('NEXT_PUBLIC_DEV_MODE', 'true');
    const { result } = renderHook(() => useApiToken());

    expect(await result.current()).toBe('dev-token');
    expect(clerkGetToken).not.toHaveBeenCalled();
    expect(isDevAuthMode()).toBe(true);
  });

  it('returns an empty string in dev mode without a stored token', async () => {
    vi.stubEnv('NODE_ENV', 'development');
    vi.stubEnv('NEXT_PUBLIC_DEV_MODE', 'true');
    window.localStorage.clear();
    const { result } = renderHook(() => useApiToken());

    expect(await result.current()).toBe('');
  });

  it('ignores dev mode in a production build', async () => {
    vi.stubEnv('NODE_ENV', 'production');
    vi.stubEnv('NEXT_PUBLIC_DEV_MODE', 'true');
    const { result } = renderHook(() => useApiToken());

    expect(await result.current()).toBe('clerk-token');
    expect(isDevAuthMode()).toBe(false);
  });

  it('no longer reads NEXT_PUBLIC_DEV_AUTH_TOKEN', async () => {
    vi.stubEnv('NODE_ENV', 'development');
    vi.stubEnv('NEXT_PUBLIC_DEV_MODE', 'true');
    vi.stubEnv('NEXT_PUBLIC_DEV_AUTH_TOKEN', 'inlined-token');
    const { result } = renderHook(() => useApiToken());

    expect(await result.current()).toBe('dev-token');
  });

  it('keeps the same function across renders while Clerk getToken is stable', () => {
    const { result, rerender } = renderHook(() => useApiToken());
    const first = result.current;
    rerender();
    expect(result.current).toBe(first);
  });
});
