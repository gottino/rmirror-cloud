import { renderHook, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { useObjectUrl } from '../../lib/useObjectUrl';

describe('useObjectUrl', () => {
  let counter = 0;
  const create = vi.fn(() => `blob:test/${++counter}`);
  const revoke = vi.fn();
  const originalCreate = URL.createObjectURL;
  const originalRevoke = URL.revokeObjectURL;

  beforeEach(() => {
    counter = 0;
    create.mockClear();
    revoke.mockClear();
    URL.createObjectURL = create;
    URL.revokeObjectURL = revoke;
  });

  afterEach(() => {
    URL.createObjectURL = originalCreate;
    URL.revokeObjectURL = originalRevoke;
  });

  it('revokes the previous URL when replaced and the last one on unmount', () => {
    const { result, unmount } = renderHook(() => useObjectUrl());
    expect(result.current[0]).toBeNull();

    act(() => result.current[1](new Blob(['a'])));
    expect(result.current[0]).toBe('blob:test/1');
    expect(revoke).not.toHaveBeenCalled();

    act(() => result.current[1](new Blob(['b'])));
    expect(result.current[0]).toBe('blob:test/2');
    expect(revoke).toHaveBeenCalledWith('blob:test/1');

    unmount();
    expect(revoke).toHaveBeenCalledWith('blob:test/2');
    expect(revoke).toHaveBeenCalledTimes(2);
  });

  it('clearing revokes the URL', () => {
    const { result } = renderHook(() => useObjectUrl());
    act(() => result.current[1](new Blob(['a'])));
    act(() => result.current[1](null));
    expect(result.current[0]).toBeNull();
    expect(revoke).toHaveBeenCalledWith('blob:test/1');
  });

  it('does not create a URL for a blob set after unmount', () => {
    const { result, unmount } = renderHook(() => useObjectUrl());
    const setBlob = result.current[1];
    unmount();
    setBlob(new Blob(['late']));
    expect(create).not.toHaveBeenCalled();
  });
});
