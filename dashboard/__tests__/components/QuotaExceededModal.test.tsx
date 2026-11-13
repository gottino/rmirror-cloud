import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { QuotaExceededModal } from '../../components/QuotaExceededModal';

const quota = {
  quota_type: 'ocr',
  used: 30,
  limit: 30,
  remaining: 0,
  percentage_used: 100,
  is_near_limit: true,
  is_exhausted: true,
  reset_at: '2026-02-01T00:00:00Z',
  period_start: '2026-01-01T00:00:00Z',
} as any;

describe('QuotaExceededModal', () => {
  it('can be closed while quota is exhausted', () => {
    const onClose = vi.fn();
    render(<QuotaExceededModal isOpen onClose={onClose} quota={quota} />);

    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
