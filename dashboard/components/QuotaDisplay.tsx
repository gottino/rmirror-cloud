'use client';

import { useQuota } from '@/lib/quota-context';
import { QUOTA_THRESHOLDS } from '@/lib/constants';
import { AlertTriangle, CheckCircle, XCircle } from 'lucide-react';

interface QuotaDisplayProps {
  variant?: 'compact' | 'full';
  onQuotaExceeded?: () => void;
}

export function QuotaDisplay({ variant = 'compact', onQuotaExceeded }: QuotaDisplayProps) {
  const { quota, loading } = useQuota();

  if (loading || !quota) {
    return null;
  }

  // Call callback if quota exceeded
  if (quota.is_exhausted && onQuotaExceeded) {
    onQuotaExceeded();
  }

  const percentage = isNaN(quota.percentage_used) ? 0 : quota.percentage_used;
  const remaining = quota.limit - quota.used;

  const getColor = () => {
    if (percentage >= QUOTA_THRESHOLDS.CRITICAL) return 'var(--destructive)';
    if (percentage >= QUOTA_THRESHOLDS.WARNING) return 'var(--amber-gold)';
    return 'var(--sage-green)';
  };

  const getIcon = () => {
    if (percentage >= QUOTA_THRESHOLDS.CRITICAL) return <XCircle className="w-4 h-4" />;
    if (percentage >= QUOTA_THRESHOLDS.WARNING) return <AlertTriangle className="w-4 h-4" />;
    return <CheckCircle className="w-4 h-4" />;
  };

  const getStatusText = () => {
    if (quota.is_exhausted) return 'Quota exhausted';
    if (quota.is_near_limit) return 'Near limit';
    return 'Available';
  };

  const formatResetDate = (dateStr: string) => {
    const date = new Date(dateStr);
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
  };

  if (variant === 'compact') {
    return (
      <div
        className="flex items-center gap-2 px-3 py-2 rounded-lg"
        style={{
          backgroundColor: 'var(--soft-cream)',
          border: '1px solid var(--border)',
          fontSize: '0.875em'
        }}
      >
        <div style={{ color: getColor() }}>
          {getIcon()}
        </div>
        <div className="flex items-center gap-1">
          <span style={{ fontWeight: 600, color: 'var(--warm-charcoal)' }}>
            {quota.used}
          </span>
          <span style={{ color: 'var(--warm-gray)' }}>
            / {quota.limit} pages used
          </span>
        </div>
      </div>
    );
  }

  return (
    <div
      className="p-4 rounded-lg"
      style={{
        backgroundColor: 'var(--card)',
        border: '1px solid var(--border)'
      }}
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <div style={{ color: getColor() }}>
            {getIcon()}
          </div>
          <h3 style={{ fontSize: '0.925em', fontWeight: 600, color: 'var(--warm-charcoal)', margin: 0 }}>
            OCR Quota
          </h3>
        </div>
        <span
          style={{
            fontSize: '0.75em',
            fontWeight: 500,
            color: getColor(),
            textTransform: 'uppercase',
            letterSpacing: '0.05em'
          }}
        >
          {getStatusText()}
        </span>
      </div>

      {/* Usage bar */}
      <div className="mb-3">
        <div
          className="h-2 rounded-full overflow-hidden"
          style={{ backgroundColor: 'var(--soft-cream)' }}
        >
          <div
            className="h-full transition-all duration-300"
            style={{
              width: `${Math.min(percentage, 100)}%`,
              backgroundColor: getColor()
            }}
          />
        </div>
      </div>

      {/* Stats */}
      <div className="flex items-center justify-between">
        <div>
          <div style={{ fontSize: '1.5rem', fontWeight: 600, color: 'var(--warm-charcoal)' }}>
            {quota.used} <span style={{ fontSize: '0.875rem', fontWeight: 400, color: 'var(--warm-gray)' }}>
              / {quota.limit}
            </span>
          </div>
          <div style={{ fontSize: '0.75em', color: 'var(--warm-gray)', marginTop: '0.25rem' }}>
            pages used this month
          </div>
        </div>
        <div className="text-right">
          <div style={{ fontSize: '0.875em', fontWeight: 500, color: 'var(--warm-charcoal)' }}>
            {remaining} remaining
          </div>
          <div style={{ fontSize: '0.75em', color: 'var(--warm-gray)', marginTop: '0.25rem' }}>
            Resets {formatResetDate(quota.reset_at)}
          </div>
        </div>
      </div>
    </div>
  );
}
