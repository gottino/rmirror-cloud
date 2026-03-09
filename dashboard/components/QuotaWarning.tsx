'use client';

import { useRef, useState } from 'react';
import { useQuota } from '@/lib/quota-context';
import { QUOTA_THRESHOLDS } from '@/lib/constants';
import { AlertTriangle, X } from 'lucide-react';
import Link from 'next/link';
import { trackEvent } from '@/lib/analytics';

interface QuotaWarningProps {
  onUpgradeClick?: () => void;
}

export function QuotaWarning({ onUpgradeClick }: QuotaWarningProps) {
  const { quota } = useQuota();
  const [dismissed, setDismissed] = useState(false);
  const trackedRef = useRef(false);

  // Don't show if dismissed or quota not near limit
  if (dismissed || !quota || isNaN(quota.percentage_used) || quota.percentage_used < QUOTA_THRESHOLDS.WARNING_VISIBLE) {
    return null;
  }

  // Track quota warning display (once per mount)
  if (!trackedRef.current) {
    trackEvent({ name: 'quota_warning_shown', data: { percent_used: Math.round(quota.percentage_used) } });
    trackedRef.current = true;
  }

  const remaining = quota.limit - quota.used;
  const isExhausted = quota.is_exhausted;

  return (
    <div
      className="px-6 lg:px-8 py-4"
      style={{
        backgroundColor: isExhausted ? 'var(--terracotta-light)' : 'var(--amber-gold-light)',
        borderBottom: '1px solid',
        borderColor: isExhausted ? 'var(--destructive)' : 'var(--amber-gold)'
      }}
    >
      <div className="max-w-full mx-auto flex items-start gap-3">
        <div style={{ color: isExhausted ? 'var(--destructive)' : 'var(--amber-gold)' }}>
          <AlertTriangle className="w-5 h-5" />
        </div>
        <div className="flex-1">
          <h4 style={{ fontSize: '0.925em', fontWeight: 600, color: 'var(--warm-charcoal)', marginBottom: '0.25rem' }}>
            {isExhausted ? 'Free Tier Quota Exhausted' : 'Approaching Quota Limit'}
          </h4>
          <p style={{ fontSize: '0.875em', color: 'var(--warm-gray)', marginBottom: '0.5rem' }}>
            {isExhausted ? (
              <>
                You&apos;ve used all {quota.limit} free pages this month. Your notebooks will continue syncing,
                but OCR transcription and integrations are paused until your quota resets on{' '}
                <strong>{new Date(quota.reset_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}</strong>.
              </>
            ) : (
              <>
                You&apos;ve used {quota.used} of {quota.limit} free pages ({Math.round(quota.percentage_used)}%).
                Only {remaining} page{remaining !== 1 ? 's' : ''} remaining this month.
              </>
            )}
          </p>
          <div className="flex items-center gap-3">
            <Link
              href="/billing"
              className="px-4 py-2 rounded-lg transition-colors"
              style={{
                backgroundColor: 'var(--primary)',
                color: 'var(--primary-foreground)',
                fontSize: '0.875em',
                fontWeight: 500,
                textDecoration: 'none',
                display: 'inline-block'
              }}
              onClick={onUpgradeClick}
            >
              {isExhausted ? 'View Upgrade Options' : 'Upgrade to Pro'}
            </Link>
            <Link
              href="/billing"
              style={{
                fontSize: '0.875em',
                color: 'var(--terracotta)',
                textDecoration: 'underline'
              }}
            >
              View quota details
            </Link>
          </div>
        </div>
        <button
          onClick={() => setDismissed(true)}
          className="p-1 rounded hover:bg-black/5 transition-colors"
          style={{ color: 'var(--warm-gray)' }}
        >
          <X className="w-5 h-5" />
        </button>
      </div>
    </div>
  );
}
