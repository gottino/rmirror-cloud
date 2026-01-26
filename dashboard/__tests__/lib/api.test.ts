import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  getQuotaStatus,
  getNotebooks,
  QuotaExceededError,
  type QuotaStatus,
} from '../../lib/api';

describe('API Client', () => {
  const mockFetch = vi.fn();
  const originalFetch = global.fetch;

  beforeEach(() => {
    global.fetch = mockFetch;
    mockFetch.mockClear();
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  describe('getQuotaStatus', () => {
    it('returns quota status on success', async () => {
      const mockQuota: QuotaStatus = {
        quota_type: 'ocr',
        used: 15,
        limit: 30,
        remaining: 15,
        percentage_used: 50,
        is_near_limit: false,
        is_exhausted: false,
        reset_at: '2026-02-01T00:00:00Z',
        period_start: '2026-01-01T00:00:00Z',
      };

      mockFetch.mockResolvedValue({
        ok: true,
        status: 200,
        json: () => Promise.resolve(mockQuota),
      });

      const result = await getQuotaStatus('test-token');

      expect(result).toEqual(mockQuota);
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/quota/status'),
        expect.objectContaining({
          headers: { Authorization: 'Bearer test-token' },
        })
      );
    });

    it('throws QuotaExceededError on 402 response', async () => {
      const mockQuota: QuotaStatus = {
        quota_type: 'ocr',
        used: 30,
        limit: 30,
        remaining: 0,
        percentage_used: 100,
        is_near_limit: true,
        is_exhausted: true,
        reset_at: '2026-02-01T00:00:00Z',
        period_start: '2026-01-01T00:00:00Z',
      };

      mockFetch.mockResolvedValue({
        ok: false,
        status: 402,
        json: () => Promise.resolve({ quota: mockQuota }),
      });

      await expect(getQuotaStatus('test-token')).rejects.toThrow(QuotaExceededError);
    });

    it('throws generic error on 500 response', async () => {
      mockFetch.mockResolvedValue({
        ok: false,
        status: 500,
        text: () => Promise.resolve('Internal Server Error'),
      });

      await expect(getQuotaStatus('test-token')).rejects.toThrow('Internal Server Error');
    });

    it('includes bearer token in request', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        status: 200,
        json: () => Promise.resolve({}),
      });

      await getQuotaStatus('my-auth-token');

      expect(mockFetch).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          headers: expect.objectContaining({
            Authorization: 'Bearer my-auth-token',
          }),
        })
      );
    });
  });

  describe('getNotebooks', () => {
    it('returns notebooks on success', async () => {
      const mockNotebooks = [
        {
          id: 1,
          visible_name: 'Test Notebook',
          document_type: 'notebook',
          notebook_uuid: 'uuid-123',
        },
      ];

      mockFetch.mockResolvedValue({
        ok: true,
        status: 200,
        json: () => Promise.resolve(mockNotebooks),
      });

      const result = await getNotebooks('test-token');

      expect(result).toEqual(mockNotebooks);
    });

    it('handles 402 quota exceeded for notebooks', async () => {
      const mockQuota: QuotaStatus = {
        quota_type: 'ocr',
        used: 30,
        limit: 30,
        remaining: 0,
        percentage_used: 100,
        is_near_limit: true,
        is_exhausted: true,
        reset_at: '2026-02-01T00:00:00Z',
        period_start: '2026-01-01T00:00:00Z',
      };

      mockFetch.mockResolvedValue({
        ok: false,
        status: 402,
        json: () => Promise.resolve({ quota: mockQuota }),
      });

      await expect(getNotebooks('test-token')).rejects.toThrow(QuotaExceededError);
    });
  });

  describe('QuotaExceededError', () => {
    it('stores quota information', () => {
      const quota: QuotaStatus = {
        quota_type: 'ocr',
        used: 30,
        limit: 30,
        remaining: 0,
        percentage_used: 100,
        is_near_limit: true,
        is_exhausted: true,
        reset_at: '2026-02-01T00:00:00Z',
        period_start: '2026-01-01T00:00:00Z',
      };

      const error = new QuotaExceededError(quota);

      expect(error.message).toBe('Quota exceeded');
      expect(error.name).toBe('QuotaExceededError');
      expect(error.quota).toEqual(quota);
    });

    it('is instance of Error', () => {
      const quota: QuotaStatus = {
        quota_type: 'ocr',
        used: 30,
        limit: 30,
        remaining: 0,
        percentage_used: 100,
        is_near_limit: true,
        is_exhausted: true,
        reset_at: '2026-02-01T00:00:00Z',
        period_start: '2026-01-01T00:00:00Z',
      };

      const error = new QuotaExceededError(quota);

      expect(error).toBeInstanceOf(Error);
      expect(error).toBeInstanceOf(QuotaExceededError);
    });
  });
});
