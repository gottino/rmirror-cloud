import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { QuotaWarning } from '../../components/QuotaWarning';

// Mock the API module
vi.mock('@/lib/api', () => ({
  getQuotaStatus: vi.fn(),
}));

import { getQuotaStatus } from '@/lib/api';

const mockGetQuotaStatus = vi.mocked(getQuotaStatus);

describe('QuotaWarning', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders nothing when quota is below 80%', async () => {
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

    const { container } = render(<QuotaWarning />);

    await waitFor(() => {
      // Should not render warning
      expect(container.firstChild).toBeNull();
    });
  });

  it('shows warning banner at 80%+ quota', async () => {
    mockGetQuotaStatus.mockResolvedValue({
      quota_type: 'ocr',
      used: 24,
      limit: 30,
      remaining: 6,
      percentage_used: 80,
      is_near_limit: true,
      is_exhausted: false,
      reset_at: '2026-02-01T00:00:00Z',
      period_start: '2026-01-01T00:00:00Z',
    });

    render(<QuotaWarning />);

    await waitFor(() => {
      expect(screen.getByText('Approaching Quota Limit')).toBeInTheDocument();
      expect(screen.getByText(/You've used 24 of 30 free pages/)).toBeInTheDocument();
    });
  });

  it('shows exhausted state at 100% quota', async () => {
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

    render(<QuotaWarning />);

    await waitFor(() => {
      expect(screen.getByText('Free Tier Quota Exhausted')).toBeInTheDocument();
      expect(screen.getByText(/You've used all 30 free pages/)).toBeInTheDocument();
    });
  });

  it('can be dismissed', async () => {
    mockGetQuotaStatus.mockResolvedValue({
      quota_type: 'ocr',
      used: 24,
      limit: 30,
      remaining: 6,
      percentage_used: 80,
      is_near_limit: true,
      is_exhausted: false,
      reset_at: '2026-02-01T00:00:00Z',
      period_start: '2026-01-01T00:00:00Z',
    });

    const { container } = render(<QuotaWarning />);

    await waitFor(() => {
      expect(screen.getByText('Approaching Quota Limit')).toBeInTheDocument();
    });

    // Find and click dismiss button
    const dismissButton = container.querySelector('button');
    expect(dismissButton).toBeInTheDocument();
    fireEvent.click(dismissButton!);

    // Should be dismissed
    await waitFor(() => {
      expect(screen.queryByText('Approaching Quota Limit')).not.toBeInTheDocument();
    });
  });

  it('has upgrade to pro link', async () => {
    mockGetQuotaStatus.mockResolvedValue({
      quota_type: 'ocr',
      used: 24,
      limit: 30,
      remaining: 6,
      percentage_used: 80,
      is_near_limit: true,
      is_exhausted: false,
      reset_at: '2026-02-01T00:00:00Z',
      period_start: '2026-01-01T00:00:00Z',
    });

    render(<QuotaWarning />);

    await waitFor(() => {
      expect(screen.getByText('Upgrade to Pro')).toBeInTheDocument();
    });

    const upgradeLink = screen.getByText('Upgrade to Pro').closest('a');
    expect(upgradeLink).toHaveAttribute('href', '/billing');
  });

  it('shows view upgrade options when exhausted', async () => {
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

    render(<QuotaWarning />);

    await waitFor(() => {
      expect(screen.getByText('View Upgrade Options')).toBeInTheDocument();
    });
  });

  it('upgrade button links to billing page', async () => {
    mockGetQuotaStatus.mockResolvedValue({
      quota_type: 'ocr',
      used: 24,
      limit: 30,
      remaining: 6,
      percentage_used: 80,
      is_near_limit: true,
      is_exhausted: false,
      reset_at: '2026-02-01T00:00:00Z',
      period_start: '2026-01-01T00:00:00Z',
    });

    render(<QuotaWarning />);

    await waitFor(() => {
      const upgradeLink = screen.getByText('Upgrade to Pro');
      expect(upgradeLink).toBeInTheDocument();
      // Verify link points to billing
      expect(upgradeLink.closest('a')).toHaveAttribute('href', '/billing');
    });
  });

  it('handles NaN percentage gracefully', async () => {
    mockGetQuotaStatus.mockResolvedValue({
      quota_type: 'ocr',
      used: 0,
      limit: 0,
      remaining: 0,
      percentage_used: NaN,
      is_near_limit: false,
      is_exhausted: false,
      reset_at: '2026-02-01T00:00:00Z',
      period_start: '2026-01-01T00:00:00Z',
    });

    const { container } = render(<QuotaWarning />);

    await waitFor(() => {
      // Should not render when percentage is NaN
      expect(container.firstChild).toBeNull();
    });
  });

  it('shows view quota details link', async () => {
    mockGetQuotaStatus.mockResolvedValue({
      quota_type: 'ocr',
      used: 24,
      limit: 30,
      remaining: 6,
      percentage_used: 80,
      is_near_limit: true,
      is_exhausted: false,
      reset_at: '2026-02-01T00:00:00Z',
      period_start: '2026-01-01T00:00:00Z',
    });

    render(<QuotaWarning />);

    await waitFor(() => {
      expect(screen.getByText('View quota details')).toBeInTheDocument();
    });

    const detailsLink = screen.getByText('View quota details').closest('a');
    expect(detailsLink).toHaveAttribute('href', '/billing');
  });
});
