import { render, screen, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { QuotaDisplay } from '../../components/QuotaDisplay';

// Mock the quota context
vi.mock('@/lib/quota-context', () => ({
  useQuota: vi.fn(),
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

describe('QuotaDisplay', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
  });

  it('renders nothing while loading', () => {
    mockUseQuota.mockReturnValue({
      quota: null,
      loading: true,
      error: null,
      refetch: vi.fn(),
    });

    const { container } = render(<QuotaDisplay />);
    expect(container.firstChild).toBeNull();
  });

  it('renders quota information when data loads', () => {
    mockUseQuota.mockReturnValue({
      quota: mockQuota() as any,
      loading: false,
      error: null,
      refetch: vi.fn(),
    });

    render(<QuotaDisplay />);

    expect(screen.getByText('15')).toBeInTheDocument();
    expect(screen.getByText(/\/ 30 pages used/)).toBeInTheDocument();
  });

  it('shows green status when quota is under 67%', () => {
    mockUseQuota.mockReturnValue({
      quota: mockQuota({ used: 10, remaining: 20, percentage_used: 33.33 }) as any,
      loading: false,
      error: null,
      refetch: vi.fn(),
    });

    render(<QuotaDisplay variant="full" />);

    expect(screen.getByText('Available')).toBeInTheDocument();
  });

  it('shows yellow/warning status when quota is between 67% and 90%', () => {
    mockUseQuota.mockReturnValue({
      quota: mockQuota({ used: 25, remaining: 5, percentage_used: 83.33, is_near_limit: true }) as any,
      loading: false,
      error: null,
      refetch: vi.fn(),
    });

    render(<QuotaDisplay variant="full" />);

    expect(screen.getByText('Near limit')).toBeInTheDocument();
  });

  it('shows red/exhausted status when quota is at 100%', () => {
    mockUseQuota.mockReturnValue({
      quota: mockQuota({ used: 30, remaining: 0, percentage_used: 100, is_near_limit: true, is_exhausted: true }) as any,
      loading: false,
      error: null,
      refetch: vi.fn(),
    });

    render(<QuotaDisplay variant="full" />);

    expect(screen.getByText('Quota exhausted')).toBeInTheDocument();
  });

  const exhausted = () =>
    mockQuota({ used: 30, remaining: 0, percentage_used: 100, is_near_limit: true, is_exhausted: true }) as any;

  it('calls onQuotaExceeded from an effect when quota is exhausted', () => {
    const onQuotaExceeded = vi.fn();
    mockUseQuota.mockReturnValue({ quota: exhausted(), loading: false, error: null, refetch: vi.fn() });

    render(<QuotaDisplay onQuotaExceeded={onQuotaExceeded} />);

    expect(onQuotaExceeded).toHaveBeenCalledTimes(1);
  });

  it('does not call onQuotaExceeded again on re-render or poll update', () => {
    const onQuotaExceeded = vi.fn();
    mockUseQuota.mockReturnValue({ quota: exhausted(), loading: false, error: null, refetch: vi.fn() });

    const { rerender } = render(<QuotaDisplay onQuotaExceeded={onQuotaExceeded} />);
    mockUseQuota.mockReturnValue({ quota: exhausted(), loading: false, error: null, refetch: vi.fn() });
    act(() => {
      rerender(<QuotaDisplay onQuotaExceeded={onQuotaExceeded} />);
      rerender(<QuotaDisplay onQuotaExceeded={() => onQuotaExceeded()} />);
    });

    expect(onQuotaExceeded).toHaveBeenCalledTimes(1);
  });

  it('does not call onQuotaExceeded when quota is not exhausted', () => {
    const onQuotaExceeded = vi.fn();
    mockUseQuota.mockReturnValue({ quota: mockQuota() as any, loading: false, error: null, refetch: vi.fn() });

    render(<QuotaDisplay onQuotaExceeded={onQuotaExceeded} />);

    expect(onQuotaExceeded).not.toHaveBeenCalled();
  });

  it('renders nothing when quota is null', () => {
    mockUseQuota.mockReturnValue({
      quota: null,
      loading: false,
      error: 'API Error',
      refetch: vi.fn(),
    });

    const { container } = render(<QuotaDisplay />);
    expect(container.firstChild).toBeNull();
  });

  it('renders compact variant correctly', () => {
    mockUseQuota.mockReturnValue({
      quota: mockQuota() as any,
      loading: false,
      error: null,
      refetch: vi.fn(),
    });

    render(<QuotaDisplay variant="compact" />);

    expect(screen.getByText('15')).toBeInTheDocument();
    expect(screen.getByText(/\/ 30 pages used/)).toBeInTheDocument();

    // Should NOT show "Available" in compact mode
    expect(screen.queryByText('Available')).not.toBeInTheDocument();
  });

  it('renders full variant with reset date', () => {
    mockUseQuota.mockReturnValue({
      quota: mockQuota() as any,
      loading: false,
      error: null,
      refetch: vi.fn(),
    });

    render(<QuotaDisplay variant="full" />);

    expect(screen.getByText('15 remaining')).toBeInTheDocument();
    expect(screen.getByText(/Resets/)).toBeInTheDocument();
  });

  it('handles NaN percentage gracefully', () => {
    mockUseQuota.mockReturnValue({
      quota: mockQuota({ used: NaN, remaining: NaN, percentage_used: NaN }) as any,
      loading: false,
      error: null,
      refetch: vi.fn(),
    });

    render(<QuotaDisplay variant="compact" />);

    // Should render without crashing
    expect(screen.getByText(/pages used/)).toBeInTheDocument();
  });
});
