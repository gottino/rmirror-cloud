'use client';

import { useEffect, useState } from 'react';
import { X, CheckCircle, Mail } from 'lucide-react';
import type { QuotaStatus } from '@/lib/api';

interface QuotaExceededModalProps {
  isOpen: boolean;
  onClose: () => void;
  quota: QuotaStatus | null;
}

export function QuotaExceededModal({ isOpen, onClose, quota }: QuotaExceededModalProps) {
  const [email, setEmail] = useState('');
  const [submitted, setSubmitted] = useState(false);

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

  const handleWaitlistSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    // TODO: Send to waitlist API endpoint
    console.log('Waitlist signup:', email);
    setSubmitted(true);
  };

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
          className="absolute top-4 right-4 p-2 rounded-lg hover:bg-black/5 transition-colors"
          style={{ color: 'var(--warm-gray)' }}
        >
          <X className="w-5 h-5" />
        </button>

        {/* Header */}
        <div className="p-8 border-b" style={{ borderColor: 'var(--border)' }}>
          <div
            className="w-12 h-12 rounded-full flex items-center justify-center mb-4"
            style={{ backgroundColor: 'rgba(200, 90, 84, 0.1)' }}
          >
            <div style={{ color: 'var(--terracotta)', fontSize: '1.5rem' }}>📊</div>
          </div>
          <h2 style={{ fontSize: '1.75rem', fontWeight: 600, color: 'var(--warm-charcoal)', marginBottom: '0.5rem' }}>
            Free Tier Limit Reached
          </h2>
          <p style={{ fontSize: '1rem', color: 'var(--warm-gray)' }}>
            You've used all {quota.limit} free pages this month
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
          <div
            className="p-6 rounded-lg relative overflow-hidden"
            style={{ backgroundColor: 'var(--card)', border: '2px solid var(--terracotta)' }}
          >
            {/* Coming soon badge */}
            <div
              className="absolute top-4 right-4 px-3 py-1 rounded-full text-xs font-semibold"
              style={{
                backgroundColor: 'var(--amber-gold)',
                color: 'white',
                textTransform: 'uppercase',
                letterSpacing: '0.05em'
              }}
            >
              Coming Soon
            </div>

            <h3 style={{ fontSize: '1.5rem', fontWeight: 600, color: 'var(--warm-charcoal)', marginBottom: '0.25rem' }}>
              Pro Tier
            </h3>
            <p style={{ fontSize: '1.125rem', color: 'var(--terracotta)', fontWeight: 500, marginBottom: '1.5rem' }}>
              Launching February 2026
            </p>

            {/* Features */}
            <div className="space-y-3 mb-6">
              {[
                '500 pages/month OCR transcription',
                'All integrations enabled',
                'Priority processing',
                'Email support'
              ].map((feature, index) => (
                <div key={index} className="flex items-start gap-3">
                  <CheckCircle className="w-5 h-5 flex-shrink-0" style={{ color: 'var(--sage-green)' }} />
                  <span style={{ fontSize: '0.925em', color: 'var(--warm-charcoal)' }}>{feature}</span>
                </div>
              ))}
            </div>

            {/* Pricing preview */}
            <div
              className="p-4 rounded-lg mb-4"
              style={{ backgroundColor: 'var(--soft-cream)' }}
            >
              <div style={{ fontSize: '0.75em', color: 'var(--warm-gray)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '0.25rem' }}>
                Expected Pricing
              </div>
              <div style={{ fontSize: '2rem', fontWeight: 600, color: 'var(--warm-charcoal)' }}>
                $9<span style={{ fontSize: '1rem', fontWeight: 400, color: 'var(--warm-gray)' }}>/month</span>
              </div>
            </div>

            {/* Waitlist form */}
            {!submitted ? (
              <form onSubmit={handleWaitlistSubmit}>
                <label style={{ fontSize: '0.875em', fontWeight: 500, color: 'var(--warm-charcoal)', display: 'block', marginBottom: '0.5rem' }}>
                  Join the Pro Waitlist
                </label>
                <div className="flex gap-2">
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="your@email.com"
                    required
                    className="flex-1 px-4 py-2 rounded-lg"
                    style={{
                      border: '1px solid var(--border)',
                      fontSize: '0.925em',
                      backgroundColor: 'var(--card)',
                      color: 'var(--foreground)'
                    }}
                  />
                  <button
                    type="submit"
                    className="px-6 py-2 rounded-lg transition-colors font-semibold"
                    style={{
                      backgroundColor: 'var(--primary)',
                      color: 'var(--primary-foreground)',
                      fontSize: '0.925em'
                    }}
                  >
                    Join Waitlist
                  </button>
                </div>
              </form>
            ) : (
              <div
                className="p-4 rounded-lg flex items-center gap-3"
                style={{ backgroundColor: 'rgba(155, 183, 162, 0.1)', border: '1px solid var(--sage-green)' }}
              >
                <CheckCircle className="w-5 h-5" style={{ color: 'var(--sage-green)' }} />
                <span style={{ fontSize: '0.925em', color: 'var(--warm-charcoal)', fontWeight: 500 }}>
                  You're on the waitlist! We'll email you when Pro tier launches.
                </span>
              </div>
            )}
          </div>

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
