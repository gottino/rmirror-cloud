'use client';

import { useState } from 'react';
import Link from 'next/link';
import { ExternalLink } from 'lucide-react';
import { trackEvent } from '@/lib/analytics';

interface TermsAcceptanceModalProps {
  onAccept: () => Promise<void>;
}

export function TermsAcceptanceModal({ onAccept }: TermsAcceptanceModalProps) {
  const [checked, setChecked] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const handleAccept = async () => {
    setSubmitting(true);
    try {
      await onAccept();
      trackEvent({ name: 'terms_accepted', data: { tos_version: '1.0' } });
    } catch (error) {
      console.error('Failed to accept terms:', error);
      setSubmitting(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center p-4"
      style={{ backgroundColor: 'rgba(0, 0, 0, 0.6)' }}
    >
      <div
        className="w-full max-w-md rounded-xl p-8"
        style={{
          background: 'var(--card)',
          boxShadow: 'var(--shadow-lg)',
        }}
      >
        <h2
          className="text-xl font-semibold mb-2"
          style={{ color: 'var(--warm-charcoal)' }}
        >
          Terms & Privacy Policy
        </h2>

        <p className="mb-6" style={{ color: 'var(--warm-gray)', fontSize: '0.925rem', lineHeight: '1.6' }}>
          Before continuing, please review and accept our Terms of Service and Privacy Policy.
        </p>

        <div className="space-y-3 mb-6">
          <Link
            href="/legal/terms"
            target="_blank"
            className="flex items-center justify-between p-3 rounded-lg transition-colors hover:opacity-80"
            style={{
              background: 'var(--soft-cream)',
              border: '1px solid var(--border)',
              color: 'var(--warm-charcoal)',
              fontSize: '0.925rem',
              fontWeight: 500,
            }}
          >
            Terms of Service
            <ExternalLink className="w-4 h-4" style={{ color: 'var(--warm-gray)' }} />
          </Link>

          <Link
            href="/legal/privacy"
            target="_blank"
            className="flex items-center justify-between p-3 rounded-lg transition-colors hover:opacity-80"
            style={{
              background: 'var(--soft-cream)',
              border: '1px solid var(--border)',
              color: 'var(--warm-charcoal)',
              fontSize: '0.925rem',
              fontWeight: 500,
            }}
          >
            Privacy Policy
            <ExternalLink className="w-4 h-4" style={{ color: 'var(--warm-gray)' }} />
          </Link>
        </div>

        <label
          className="flex items-start gap-3 mb-6 cursor-pointer select-none"
          style={{ fontSize: '0.875rem', color: 'var(--warm-charcoal)' }}
        >
          <input
            type="checkbox"
            checked={checked}
            onChange={(e) => setChecked(e.target.checked)}
            className="mt-0.5 w-4 h-4 rounded"
            style={{ accentColor: 'var(--terracotta)' }}
          />
          <span>
            I have read and agree to the Terms of Service and Privacy Policy.
          </span>
        </label>

        <button
          onClick={handleAccept}
          disabled={!checked || submitting}
          className="w-full py-2.5 rounded-lg font-semibold text-sm transition-all"
          style={{
            background: checked ? 'var(--terracotta)' : 'var(--border)',
            color: checked ? 'white' : 'var(--warm-gray)',
            opacity: submitting ? 0.6 : 1,
            cursor: checked && !submitting ? 'pointer' : 'not-allowed',
          }}
        >
          {submitting ? 'Accepting...' : 'Continue'}
        </button>
      </div>
    </div>
  );
}
