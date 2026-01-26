import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { QuotaDisplay } from '../../components/QuotaDisplay';

// Mock the API module
vi.mock('@/lib/api', () => ({
  getQuotaStatus: vi.fn(),
}));

import { getQuotaStatus } from '@/lib/api';

const mockGetQuotaStatus = vi.mocked(getQuotaStatus);

describe('QuotaDisplay', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders nothing while loading', () => {
    mockGetQuotaStatus.mockImplementation(() => new Promise(() => {})); // Never resolves
    const { container } = render(<QuotaDisplay />);
    expect(container.firstChild).toBeNull();
  });

  it('renders quota information when data loads', async () => {
    mockGetQuotaStatus.mockResolvedValue({
      quota_type: 'ocr',
      used: 15,
      limit: 30,
      remaining: 15,
      percentage_used: 50,
      is_near_limit: false,
      is_exhausted: false,
      reset_at: '2026-02-01T00:00:00Z',
      period_start: '2026-01-01T00:00:00Z',
    });

    render(<QuotaDisplay />);

    await waitFor(() => {
      expect(screen.getByText('15')).toBeInTheDocument();
      expect(screen.getByText(/\/ 30 pages used/)).toBeInTheDocument();
    });
  });

  it('shows green status when quota is under 67%', async () => {
    mockGetQuotaStatus.mockResolvedValue({
      quota_type: 'ocr',
      used: 10,
      limit: 30,
      remaining: 20,
      percentage_used: 33.33,
      is_near_limit: false,
      is_exhausted: false,
      reset_at: '2026-02-01T00:00:00Z',
      period_start: '2026-01-01T00:00:00Z',
    });

    render(<QuotaDisplay variant="full" />);

    await waitFor(() => {
      expect(screen.getByText('Available')).toBeInTheDocument();
    });
  });

  it('shows yellow/warning status when quota is between 67% and 90%', async () => {
    mockGetQuotaStatus.mockResolvedValue({
      quota_type: 'ocr',
      used: 25,
      limit: 30,
      remaining: 5,
      percentage_used: 83.33,
      is_near_limit: true,
      is_exhausted: false,
      reset_at: '2026-02-01T00:00:00Z',
      period_start: '2026-01-01T00:00:00Z',
    });

    render(<QuotaDisplay variant="full" />);

    await waitFor(() => {
      expect(screen.getByText('Near limit')).toBeInTheDocument();
    });
  });

  it('shows red/exhausted status when quota is at 100%', async () => {
    mockGetQuotaStatus.mockResolvedValue({
      quota_type: 'ocr',
      used: 30,
      limit: 30,
      remaining: 0,
      percentage_used: 100,
      is_near_limit: true,
      is_exhausted: true,
      reset_at: '2026-02-01T00:00:00Z',
      period_start: '2026-01-01T00:00:00Z',
    });

    render(<QuotaDisplay variant="full" />);

    await waitFor(() => {
      expect(screen.getByText('Quota exhausted')).toBeInTheDocument();
    });
  });

  it('calls onQuotaExceeded callback when quota is exhausted', async () => {
    const onQuotaExceeded = vi.fn();

    mockGetQuotaStatus.mockResolvedValue({
      quota_type: 'ocr',
      used: 30,
      limit: 30,
      remaining: 0,
      percentage_used: 100,
      is_near_limit: true,
      is_exhausted: true,
      reset_at: '2026-02-01T00:00:00Z',
      period_start: '2026-01-01T00:00:00Z',
    });

    render(<QuotaDisplay onQuotaExceeded={onQuotaExceeded} />);

    await waitFor(() => {
      expect(onQuotaExceeded).toHaveBeenCalled();
    });
  });

  it('renders nothing on API error', async () => {
    mockGetQuotaStatus.mockRejectedValue(new Error('API Error'));

    const { container } = render(<QuotaDisplay />);

    // Wait for error state
    await waitFor(() => {
      expect(container.firstChild).toBeNull();
    });
  });

  it('renders compact variant correctly', async () => {
    mockGetQuotaStatus.mockResolvedValue({
      quota_type: 'ocr',
      used: 15,
      limit: 30,
      remaining: 15,
      percentage_used: 50,
      is_near_limit: false,
      is_exhausted: false,
      reset_at: '2026-02-01T00:00:00Z',
      period_start: '2026-01-01T00:00:00Z',
    });

    render(<QuotaDisplay variant="compact" />);

    await waitFor(() => {
      expect(screen.getByText('15')).toBeInTheDocument();
      expect(screen.getByText(/\/ 30 pages used/)).toBeInTheDocument();
    });

    // Should NOT show "Available" in compact mode
    expect(screen.queryByText('Available')).not.toBeInTheDocument();
  });

  it('renders full variant with reset date', async () => {
    mockGetQuotaStatus.mockResolvedValue({
      quota_type: 'ocr',
      used: 15,
      limit: 30,
      remaining: 15,
      percentage_used: 50,
      is_near_limit: false,
      is_exhausted: false,
      reset_at: '2026-02-01T00:00:00Z',
      period_start: '2026-01-01T00:00:00Z',
    });

    render(<QuotaDisplay variant="full" />);

    await waitFor(() => {
      expect(screen.getByText('15 remaining')).toBeInTheDocument();
      expect(screen.getByText(/Resets/)).toBeInTheDocument();
    });
  });

  it('handles NaN percentage gracefully', async () => {
    mockGetQuotaStatus.mockResolvedValue({
      quota_type: 'ocr',
      used: NaN,
      limit: 30,
      remaining: NaN,
      percentage_used: NaN,
      is_near_limit: false,
      is_exhausted: false,
      reset_at: '2026-02-01T00:00:00Z',
      period_start: '2026-01-01T00:00:00Z',
    });

    render(<QuotaDisplay variant="compact" />);

    await waitFor(() => {
      // Should render without crashing
      expect(screen.getByText(/pages used/)).toBeInTheDocument();
    });
  });
});
