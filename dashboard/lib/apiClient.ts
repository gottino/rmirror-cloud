/**
 * The single HTTP entry point for the rMirror backend.
 *
 * Every function in lib/api.ts goes through `apiFetch`, so the API base URL,
 * auth header, FastAPI error parsing and the 402 quota contract live here only.
 */
import type { QuotaStatus } from './api';

export const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'https://rmirror.io/api/v1';

export type QueryValue = string | number | boolean | null | undefined;

export interface ApiFetchOptions {
  /** Bearer token; omitted for public endpoints. */
  token?: string | null;
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  /** Sent as JSON (sets Content-Type). */
  body?: unknown;
  /** Query parameters; null/undefined values are skipped. */
  query?: Record<string, QueryValue>;
  signal?: AbortSignal;
  /** How to read a successful response (default: parsed JSON). */
  responseType?: 'json' | 'blob' | 'response' | 'void';
  /** Fixed `ApiError.message` for any non-2xx response (the detail is still parsed). */
  errorMessage?: string;
  /** `ApiError.message` when the body carries no FastAPI `detail` message. */
  fallbackMessage?: string | ((status: number) => string);
}

/** A non-2xx response from the backend. `detail` is FastAPI's `detail` field, if any. */
export class ApiError extends Error {
  readonly status: number;
  readonly statusText: string;
  readonly detail: unknown;

  constructor(status: number, message: string, detail?: unknown, statusText: string = '') {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.statusText = statusText;
    this.detail = detail;
  }
}

/** HTTP 402 with the backend's `{"detail": {"message", "quota"}}` body. */
export class QuotaExceededError extends ApiError {
  quota: QuotaStatus;

  constructor(quota: QuotaStatus, detail?: unknown) {
    super(402, 'Quota exceeded', detail ?? { quota });
    this.name = 'QuotaExceededError';
    this.quota = quota;
  }
}

export function buildApiUrl(path: string, query?: Record<string, QueryValue>): string {
  const params = new URLSearchParams();
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value !== undefined && value !== null) params.set(key, String(value));
    }
  }
  const qs = params.toString();
  return `${API_BASE_URL}${path}${qs ? `?${qs}` : ''}`;
}

function detailMessage(detail: unknown): string | null {
  if (typeof detail === 'string' && detail) return detail;
  if (detail && typeof detail === 'object') {
    const message = (detail as { message?: unknown }).message;
    if (typeof message === 'string' && message) return message;
  }
  return null;
}

async function toApiError(response: Response, options: ApiFetchOptions): Promise<ApiError> {
  const statusText = response.statusText ?? '';

  // 402: the quota contract is {"detail": {"message": "...", "quota": {...}}}
  if (response.status === 402) {
    const data = await response.json().catch(() => null);
    const detail = data?.detail;
    if (detail?.quota) return new QuotaExceededError(detail.quota, detail);
    return new ApiError(402, options.errorMessage ?? 'Quota exceeded', detail, statusText);
  }

  let text = '';
  try {
    text = await response.text();
  } catch {
    // unreadable body: fall through to the generic message
  }
  let detail: unknown;
  try {
    detail = text ? JSON.parse(text)?.detail : undefined;
  } catch {
    detail = undefined;
  }

  const { fallbackMessage } = options;
  const message =
    options.errorMessage ??
    detailMessage(detail) ??
    (typeof fallbackMessage === 'function' ? fallbackMessage(response.status) : fallbackMessage) ??
    (text || `API error: ${response.status}`);
  return new ApiError(response.status, message, detail, statusText);
}

export async function apiFetch<T = unknown>(path: string, options: ApiFetchOptions = {}): Promise<T> {
  const { token, method, body, query, signal, responseType = 'json' } = options;

  const headers: Record<string, string> = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body !== undefined) headers['Content-Type'] = 'application/json';

  const init: RequestInit = { headers };
  if (method && method !== 'GET') init.method = method;
  if (body !== undefined) init.body = JSON.stringify(body);
  if (signal) init.signal = signal;

  const response = await fetch(buildApiUrl(path, query), init);

  if (!response.ok) {
    throw await toApiError(response, options);
  }

  switch (responseType) {
    case 'response':
      return response as unknown as T;
    case 'blob':
      return (await response.blob()) as unknown as T;
    case 'void':
      return undefined as T;
    default:
      return (await response.json()) as T;
  }
}

/** Filename from a `Content-Disposition: attachment; filename="..."` header. */
export function filenameFromResponse(response: Response): string | null {
  const header = response.headers.get('Content-Disposition');
  return header?.match(/filename="([^"]+)"/)?.[1] ?? null;
}
