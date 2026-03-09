'use client';

import { useState } from 'react';
import { CheckCircle } from 'lucide-react';
import { PRO_TIER } from '@/lib/constants';
import { trackEvent } from '@/lib/analytics';

interface ProTierInfoCardProps {
  variant?: 'default' | 'billing';
  showPriceDetail?: boolean;
  analyticsSource?: string;
}

export function ProTierInfoCard({
  variant = 'default',
  showPriceDetail = false,
  analyticsSource = 'unknown',
}: ProTierInfoCardProps) {
  const [email, setEmail] = useState('');
  const [submitted, setSubmitted] = useState(false);

  const features = variant === 'billing' ? PRO_TIER.featuresBilling : PRO_TIER.features;

  const handleWaitlistSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    console.log('Waitlist signup:', email);
    trackEvent({ name: 'pro_waitlist_signup', data: { source: analyticsSource } });
    setSubmitted(true);
  };

  return (
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
          letterSpacing: '0.05em',
        }}
      >
        Coming Soon
      </div>

      <h3 style={{ fontSize: '1.5rem', fontWeight: 600, color: 'var(--warm-charcoal)', marginBottom: '0.25rem' }}>
        Pro Tier
      </h3>
      <p style={{ fontSize: '1.125rem', color: 'var(--terracotta)', fontWeight: 500, marginBottom: '1.5rem' }}>
        Launching {PRO_TIER.launchDate}
      </p>

      {/* Features */}
      <div className="space-y-3 mb-6">
        {features.map((feature, index) => (
          <div key={index} className="flex items-start gap-3">
            <CheckCircle className="w-5 h-5 flex-shrink-0" style={{ color: 'var(--sage-green)' }} />
            <span style={{ fontSize: '0.925em', color: 'var(--warm-charcoal)' }}>{feature}</span>
          </div>
        ))}
      </div>

      {/* Pricing */}
      <div className="p-4 rounded-lg mb-4" style={{ backgroundColor: 'var(--soft-cream)' }}>
        <div style={{ fontSize: '0.75em', color: 'var(--warm-gray)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '0.25rem' }}>
          Expected Pricing
        </div>
        <div style={{ fontSize: variant === 'billing' ? '2.5rem' : '2rem', fontWeight: 600, color: 'var(--warm-charcoal)' }}>
          ${PRO_TIER.price}
          <span style={{ fontSize: variant === 'billing' ? '1.25rem' : '1rem', fontWeight: 400, color: 'var(--warm-gray)' }}>/month</span>
        </div>
        {showPriceDetail && (
          <p style={{ fontSize: '0.875em', color: 'var(--warm-gray)', marginTop: '0.5rem', marginBottom: 0 }}>
            ~$0.018 per page &middot; Cancel anytime
          </p>
        )}
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
                color: 'var(--foreground)',
              }}
            />
            <button
              type="submit"
              className="px-6 py-2 rounded-lg transition-colors font-semibold"
              style={{
                backgroundColor: 'var(--primary)',
                color: 'var(--primary-foreground)',
                fontSize: '0.925em',
              }}
            >
              Join Waitlist
            </button>
          </div>
          {variant === 'billing' && (
            <p style={{ fontSize: '0.75em', color: 'var(--warm-gray)', marginTop: '0.5rem', marginBottom: 0 }}>
              Be the first to know when Pro tier launches
            </p>
          )}
        </form>
      ) : (
        <div
          className="p-4 rounded-lg flex items-center gap-3"
          style={{ backgroundColor: 'var(--sage-green-light)', border: '1px solid var(--sage-green)' }}
        >
          <CheckCircle className="w-5 h-5" style={{ color: 'var(--sage-green)' }} />
          <span style={{ fontSize: '0.925em', color: 'var(--warm-charcoal)', fontWeight: 500 }}>
            You&apos;re on the waitlist! We&apos;ll email you when Pro tier launches.
          </span>
        </div>
      )}
    </div>
  );
}
