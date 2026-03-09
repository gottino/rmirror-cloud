import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { QuotaWarning } from '../../components/QuotaWarning';

// Mock the quota context
vi.mock('@/lib/quota-context', () => ({
  useQuota: vi.fn(),
}));

// Mock analytics
vi.mock('@/lib/analytics', () => ({
  trackEvent: vi.fn(),
}));

import { useQuota } from '@/lib/quota-context';

const mockUseQuota = vi.mocked(useQuota);

function mockQuota(overrides: Record<string, unknown> = {}) {
  const defaults = {
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
  return { ...defaults, ...overrides };
}

describe('QuotaWarning', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders nothing when quota is below 80%', () => {
    mockUseQuota.mockReturnValue({
      quota: mockQuota({ percentage_used: 50, is_near_limit: false }) as any,
      loading: false,
      error: null,
      refetch: vi.fn(),
    });

    const { container } = render(<QuotaWarning />);
    expect(container.firstChild).toBeNull();
  });

  it('shows warning banner at 80%+ quota', () => {
    mockUseQuota.mockReturnValue({
      quota: mockQuota({ used: 24, remaining: 6, percentage_used: 80, is_near_limit: true }) as any,
      loading: false,
      error: null,
      refetch: vi.fn(),
    });

    render(<QuotaWarning />);

    expect(screen.getByText('Approaching Quota Limit')).toBeInTheDocument();
    expect(screen.getByText(/You've used 24 of 30 free pages/)).toBeInTheDocument();
  });

  it('shows exhausted state at 100% quota', () => {
    mockUseQuota.mockReturnValue({
      quota: mockQuota({ used: 30, remaining: 0, percentage_used: 100, is_near_limit: true, is_exhausted: true }) as any,
      loading: false,
      error: null,
      refetch: vi.fn(),
    });

    render(<QuotaWarning />);

    expect(screen.getByText('Free Tier Quota Exhausted')).toBeInTheDocument();
    expect(screen.getByText(/You've used all 30 free pages/)).toBeInTheDocument();
  });

  it('can be dismissed', () => {
    mockUseQuota.mockReturnValue({
      quota: mockQuota({ used: 24, remaining: 6, percentage_used: 80, is_near_limit: true }) as any,
      loading: false,
      error: null,
      refetch: vi.fn(),
    });

    const { container } = render(<QuotaWarning />);

    expect(screen.getByText('Approaching Quota Limit')).toBeInTheDocument();

    // Find and click dismiss button
    const dismissButton = container.querySelector('button');
    expect(dismissButton).toBeInTheDocument();
    fireEvent.click(dismissButton!);

    // Should be dismissed
    expect(screen.queryByText('Approaching Quota Limit')).not.toBeInTheDocument();
  });

  it('has upgrade to pro link', () => {
    mockUseQuota.mockReturnValue({
      quota: mockQuota({ used: 24, remaining: 6, percentage_used: 80, is_near_limit: true }) as any,
      loading: false,
      error: null,
      refetch: vi.fn(),
    });

    render(<QuotaWarning />);

    expect(screen.getByText('Upgrade to Pro')).toBeInTheDocument();
    const upgradeLink = screen.getByText('Upgrade to Pro').closest('a');
    expect(upgradeLink).toHaveAttribute('href', '/billing');
  });

  it('shows view upgrade options when exhausted', () => {
    mockUseQuota.mockReturnValue({
      quota: mockQuota({ used: 30, remaining: 0, percentage_used: 100, is_near_limit: true, is_exhausted: true }) as any,
      loading: false,
      error: null,
      refetch: vi.fn(),
    });

    render(<QuotaWarning />);

    expect(screen.getByText('View Upgrade Options')).toBeInTheDocument();
  });

  it('upgrade button links to billing page', () => {
    mockUseQuota.mockReturnValue({
      quota: mockQuota({ used: 24, remaining: 6, percentage_used: 80, is_near_limit: true }) as any,
      loading: false,
      error: null,
      refetch: vi.fn(),
    });

    render(<QuotaWarning />);

    const upgradeLink = screen.getByText('Upgrade to Pro');
    expect(upgradeLink).toBeInTheDocument();
    expect(upgradeLink.closest('a')).toHaveAttribute('href', '/billing');
  });

  it('handles NaN percentage gracefully', () => {
    mockUseQuota.mockReturnValue({
      quota: mockQuota({ used: 0, limit: 0, remaining: 0, percentage_used: NaN, is_near_limit: false }) as any,
      loading: false,
      error: null,
      refetch: vi.fn(),
    });

    const { container } = render(<QuotaWarning />);
    // Should not render when percentage is NaN
    expect(container.firstChild).toBeNull();
  });

  it('shows view quota details link', () => {
    mockUseQuota.mockReturnValue({
      quota: mockQuota({ used: 24, remaining: 6, percentage_used: 80, is_near_limit: true }) as any,
      loading: false,
      error: null,
      refetch: vi.fn(),
    });

    render(<QuotaWarning />);

    expect(screen.getByText('View quota details')).toBeInTheDocument();
    const detailsLink = screen.getByText('View quota details').closest('a');
    expect(detailsLink).toHaveAttribute('href', '/billing');
  });
});
