import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  apiFetch,
  buildApiUrl,
  ApiError,
  QuotaExceededError,
  API_BASE_URL,
} from '../../lib/apiClient';

/** The error a promise rejects with (fails the test if it resolves). */
async function rejection(promise: Promise<unknown>): Promise<QuotaExceededError> {
  try {
    await promise;
  } catch (e) {
    return e as QuotaExceededError;
  }
  throw new Error('expected the request to fail');
}

function jsonResponse(status: number, body: unknown, statusText = ''): Response {
  return new Response(JSON.stringify(body), {
    status,
    statusText,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('apiFetch', () => {
  const mockFetch = vi.fn();
  const originalFetch = global.fetch;

  beforeEach(() => {
    global.fetch = mockFetch;
    mockFetch.mockReset();
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it('returns parsed JSON and sends the bearer token', async () => {
    mockFetch.mockResolvedValue(jsonResponse(200, { ok: 1 }));

    const data = await apiFetch<{ ok: number }>('/things', { token: 'tok' });

    expect(data).toEqual({ ok: 1 });
    expect(mockFetch).toHaveBeenCalledWith(`${API_BASE_URL}/things`, {
      headers: { Authorization: 'Bearer tok' },
    });
  });

  it('omits the Authorization header without a token', async () => {
    mockFetch.mockResolvedValue(jsonResponse(200, {}));

    await apiFetch('/public');

    expect(mockFetch.mock.calls[0][1].headers).toEqual({});
  });

  it('sends a JSON body with method and Content-Type', async () => {
    mockFetch.mockResolvedValue(jsonResponse(200, {}));

    await apiFetch('/things', { token: 't', method: 'POST', body: { a: 1 } });

    expect(mockFetch.mock.calls[0][1]).toEqual({
      method: 'POST',
      headers: { Authorization: 'Bearer t', 'Content-Type': 'application/json' },
      body: '{"a":1}',
    });
  });

  it('builds the query string and skips null/undefined values', async () => {
    mockFetch.mockResolvedValue(jsonResponse(200, {}));

    await apiFetch('/search', { query: { q: 'a b', skip: 0, limit: undefined, x: null, flag: false } });

    expect(mockFetch.mock.calls[0][0]).toBe(`${API_BASE_URL}/search?q=a+b&skip=0&flag=false`);
    expect(buildApiUrl('/p', { a: undefined })).toBe(`${API_BASE_URL}/p`);
  });

  it('uses a string FastAPI detail as the error message', async () => {
    mockFetch.mockResolvedValue(jsonResponse(404, { detail: 'Notebook not found' }, 'Not Found'));

    const err = await rejection(apiFetch('/notebooks/1', { token: 't' }));

    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({
      status: 404,
      statusText: 'Not Found',
      detail: 'Notebook not found',
      message: 'Notebook not found',
    });
  });

  it('uses detail.message when detail is an object', async () => {
    const detail = { message: 'Invalid thing', code: 'bad' };
    mockFetch.mockResolvedValue(jsonResponse(400, { detail }));

    const err = await rejection(apiFetch('/x'));

    expect(err).toBeInstanceOf(ApiError);
    expect(err.detail).toEqual(detail);
    expect(err.message).toBe('Invalid thing');
  });

  it('throws QuotaExceededError for a 402 with detail.quota', async () => {
    const quota = { used: 30, limit: 30, is_exhausted: true };
    mockFetch.mockResolvedValue(jsonResponse(402, { detail: { message: 'Quota exceeded', quota } }));

    const err = await rejection(apiFetch('/x'));

    expect(err).toBeInstanceOf(QuotaExceededError);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(402);
    expect(err.quota).toEqual(quota);
    expect(err.message).toBe('Quota exceeded');
  });

  it('throws a plain ApiError for a 402 without detail.quota', async () => {
    mockFetch.mockResolvedValue(jsonResponse(402, { detail: 'Payment required' }));

    const err = await rejection(apiFetch('/x'));

    expect(err).toBeInstanceOf(ApiError);
    expect(err).not.toBeInstanceOf(QuotaExceededError);
    expect(err.status).toBe(402);
    expect(err.message).toBe('Quota exceeded');
  });

  it('uses the raw text of a non-JSON error body', async () => {
    mockFetch.mockResolvedValue(new Response('Bad Gateway', { status: 502 }));

    const err = await rejection(apiFetch('/x'));

    expect(err).toBeInstanceOf(ApiError);
    expect(err.detail).toBeUndefined();
    expect(err.message).toBe('Bad Gateway');
  });

  it('falls back to the status code for an empty error body', async () => {
    mockFetch.mockResolvedValue(new Response('', { status: 500 }));

    await expect(apiFetch('/x')).rejects.toThrow('API error: 500');
  });

  it('errorMessage fixes the message but keeps the parsed detail', async () => {
    mockFetch.mockResolvedValue(jsonResponse(500, { detail: 'boom' }));

    const err = await rejection(apiFetch('/x', { errorMessage: 'Failed to load' }));

    expect(err.message).toBe('Failed to load');
    expect(err.detail).toBe('boom');
  });

  it('fallbackMessage applies only when there is no detail', async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse(500, { detail: 'specific' }));
    mockFetch.mockResolvedValueOnce(new Response('<html>oops</html>', { status: 502 }));
    mockFetch.mockResolvedValueOnce(jsonResponse(503, {}));

    await expect(apiFetch('/x', { fallbackMessage: 'Generic' })).rejects.toThrow('specific');
    await expect(apiFetch('/x', { fallbackMessage: 'Generic' })).rejects.toThrow('Generic');
    await expect(
      apiFetch('/x', { fallbackMessage: (status) => `Failed (${status})` })
    ).rejects.toThrow('Failed (503)');
  });

  it('returns a Blob, the raw Response, or nothing when asked', async () => {
    mockFetch.mockResolvedValueOnce(new Response('pdf-bytes', { status: 200 }));
    const blob = await apiFetch<Blob>('/x', { responseType: 'blob' });
    expect(await blob.text()).toBe('pdf-bytes');

    const raw = new Response('r', { status: 200 });
    mockFetch.mockResolvedValueOnce(raw);
    expect(await apiFetch<Response>('/x', { responseType: 'response' })).toBe(raw);

    mockFetch.mockResolvedValueOnce(new Response(null, { status: 204 }));
    expect(await apiFetch('/x', { responseType: 'void' })).toBeUndefined();
  });

  it('passes the abort signal to fetch and propagates the abort', async () => {
    const controller = new AbortController();
    mockFetch.mockImplementation((_url: string, init: RequestInit) =>
      new Promise((_resolve, reject) => {
        init.signal?.addEventListener('abort', () =>
          reject(new DOMException('The operation was aborted.', 'AbortError'))
        );
      })
    );

    const promise = apiFetch('/slow', { signal: controller.signal });
    controller.abort();

    await expect(promise).rejects.toMatchObject({ name: 'AbortError' });
    expect(mockFetch.mock.calls[0][1].signal).toBe(controller.signal);
  });
});
