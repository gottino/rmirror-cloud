'use client';

import { CheckCircle } from 'lucide-react';
import { PRO_TIER } from '@/lib/constants';

interface ProTierInfoCardProps {
  variant?: 'default' | 'billing';
  showPriceDetail?: boolean;
}

export function ProTierInfoCard({
  variant = 'default',
  showPriceDetail = false,
}: ProTierInfoCardProps) {
  const features = variant === 'billing' ? PRO_TIER.featuresBilling : PRO_TIER.features;

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
      <div className="p-4 rounded-lg" style={{ backgroundColor: 'var(--soft-cream)' }}>
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

    </div>
  );
}
