'use client';

import { useAuth } from '@clerk/nextjs';
import { useEffect, useState } from 'react';
import { getQuotaStatus, type QuotaStatus } from '@/lib/api';
import { AlertTriangle, CheckCircle, XCircle } from 'lucide-react';

interface QuotaDisplayProps {
  variant?: 'compact' | 'full';
  onQuotaExceeded?: () => void;
}

export function QuotaDisplay({ variant = 'compact', onQuotaExceeded }: QuotaDisplayProps) {
  const { getToken, isSignedIn } = useAuth();
  const [quota, setQuota] = useState<QuotaStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Development mode bypass
  const isDevelopmentMode = process.env.NEXT_PUBLIC_DEV_MODE === 'true';
  const effectiveIsSignedIn = isDevelopmentMode || isSignedIn;

  const fetchQuota = async () => {
    if (!effectiveIsSignedIn) {
      setLoading(false);
      return;
    }

    try {
      setError(null);
      const token = isDevelopmentMode
        ? process.env.NEXT_PUBLIC_DEV_AUTH_TOKEN || localStorage.getItem('dev_auth_token') || ''
        : await getToken();

      if (!token) {
        throw new Error('Failed to get authentication token');
      }

      const data = await getQuotaStatus(token);
      setQuota(data);

      // Call callback if quota exceeded
      if (data.is_exhausted && onQuotaExceeded) {
        onQuotaExceeded();
      }
    } catch (err) {
      console.error('Error fetching quota:', err);
      setError(err instanceof Error ? err.message : 'Failed to fetch quota');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchQuota();
    // Poll every 60 seconds to update quota
    const interval = setInterval(fetchQuota, 60000);
    return () => clearInterval(interval);
  }, [effectiveIsSignedIn]);

  if (loading || !quota) {
    return null;
  }

  if (error) {
    return null;
  }

  const percentage = isNaN(quota.percentage_used) ? 0 : quota.percentage_used;
  const remaining = quota.limit - quota.used;

  // Color coding based on percentage
  const getColor = () => {
    if (percentage >= 91) return 'var(--destructive)'; // Red
    if (percentage >= 67) return 'var(--amber-gold)'; // Yellow/Amber
    return 'var(--sage-green)'; // Green
  };

  const getIcon = () => {
    if (percentage >= 91) return <XCircle className="w-4 h-4" />;
    if (percentage >= 67) return <AlertTriangle className="w-4 h-4" />;
    return <CheckCircle className="w-4 h-4" />;
  };

  const getStatusText = () => {
    if (quota.is_exhausted) return 'Quota exhausted';
    if (quota.is_near_limit) return 'Near limit';
    return 'Available';
  };

  // Format reset date
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
