'use client';

import { useEffect } from 'react';
import { X } from 'lucide-react';
import type { QuotaStatus } from '@/lib/api';
import { ProTierInfoCard } from '@/components/ProTierInfoCard';

interface QuotaExceededModalProps {
  isOpen: boolean;
  onClose: () => void;
  quota: QuotaStatus | null;
}

export function QuotaExceededModal({ isOpen, onClose, quota }: QuotaExceededModalProps) {
  // Close on Escape key
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    if (isOpen) {
      document.addEventListener('keydown', handleEscape);
      document.body.style.overflow = 'hidden';
    }
    return () => {
      document.removeEventListener('keydown', handleEscape);
      document.body.style.overflow = 'unset';
    };
  }, [isOpen, onClose]);

  if (!isOpen || !quota) return null;

  const formatResetDate = (dateStr: string) => {
    const date = new Date(dateStr);
    return date.toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' });
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ backgroundColor: 'rgba(0, 0, 0, 0.5)' }}
      onClick={onClose}
    >
      <div
        className="relative max-w-2xl w-full rounded-lg shadow-2xl overflow-hidden"
        style={{ backgroundColor: 'var(--card)', maxHeight: '90vh', overflowY: 'auto' }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Close button */}
        <button
          onClick={onClose}
          className="absolute top-4 right-4 p-2 rounded-lg hover:bg-black/5 transition-colors z-10"
          style={{ color: 'var(--warm-gray)' }}
        >
          <X className="w-5 h-5" />
        </button>

        {/* Header */}
        <div className="p-8 border-b" style={{ borderColor: 'var(--border)' }}>
          <div
            className="w-12 h-12 rounded-full flex items-center justify-center mb-4"
            style={{ backgroundColor: 'var(--terracotta-light)' }}
          >
            <div style={{ color: 'var(--terracotta)', fontSize: '1.5rem' }}>📊</div>
          </div>
          <h2 style={{ fontSize: '1.75rem', fontWeight: 600, color: 'var(--warm-charcoal)', marginBottom: '0.5rem' }}>
            Free Tier Limit Reached
          </h2>
          <p style={{ fontSize: '1rem', color: 'var(--warm-gray)' }}>
            You&apos;ve used all {quota.limit} free pages this month
          </p>
        </div>

        {/* Content */}
        <div className="p-8">
          {/* Current status */}
          <div
            className="p-4 rounded-lg mb-6"
            style={{ backgroundColor: 'var(--soft-cream)', border: '1px solid var(--border)' }}
          >
            <p style={{ fontSize: '0.925em', color: 'var(--warm-charcoal)', marginBottom: '0.5rem' }}>
              <strong>What happens now:</strong>
            </p>
            <ul style={{ fontSize: '0.875em', color: 'var(--warm-gray)', paddingLeft: '1.25rem', margin: 0 }}>
              <li>✓ Your notebooks will continue syncing to the cloud</li>
              <li>✓ PDFs remain available for viewing in the dashboard</li>
              <li>✗ OCR transcription is paused</li>
              <li>✗ Integrations (Notion, Readwise) are paused</li>
            </ul>
            <p style={{ fontSize: '0.875em', color: 'var(--warm-gray)', marginTop: '0.75rem', marginBottom: 0 }}>
              Your quota will reset on <strong>{formatResetDate(quota.reset_at)}</strong>
            </p>
          </div>

          {/* Pro tier preview */}
          <ProTierInfoCard analyticsSource="quota_modal" />

          {/* Beta tester note */}
          <div
            className="mt-6 p-4 rounded-lg"
            style={{ backgroundColor: 'var(--soft-cream)', border: '1px solid var(--border)' }}
          >
            <p style={{ fontSize: '0.875em', color: 'var(--warm-charcoal)', marginBottom: '0.25rem' }}>
              <strong>Beta tester who needs more pages?</strong>
            </p>
            <p style={{ fontSize: '0.875em', color: 'var(--warm-gray)', margin: 0 }}>
              <a
                href="mailto:support@rmirror.io"
                style={{ color: 'var(--terracotta)', textDecoration: 'underline' }}
              >
                Contact us
              </a>
              {' '}for early access to increased quota.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
