'use client';

import { useAuth } from '@clerk/nextjs';
import UserMenu from '@/components/UserMenu';
import { useEffect, useState } from 'react';
import { CheckCircle, Menu } from 'lucide-react';
import { getQuotaStatus, type QuotaStatus } from '@/lib/api';
import { QuotaDisplay } from '@/components/QuotaDisplay';
import Sidebar from '@/components/Sidebar';
import { trackEvent } from '@/lib/analytics';

export default function BillingPage() {
  const { getToken, isSignedIn } = useAuth();
  const [quota, setQuota] = useState<QuotaStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [email, setEmail] = useState('');
  const [submitted, setSubmitted] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);

  // Development mode bypass
  const isDevelopmentMode = process.env.NEXT_PUBLIC_DEV_MODE === 'true';
  const effectiveIsSignedIn = isDevelopmentMode || isSignedIn;

  const fetchQuota = async () => {
    if (!effectiveIsSignedIn) {
      setLoading(false);
      return;
    }

    try {
      const token = isDevelopmentMode
        ? process.env.NEXT_PUBLIC_DEV_AUTH_TOKEN || localStorage.getItem('dev_auth_token') || ''
        : await getToken();

      if (!token) {
        throw new Error('Failed to get authentication token');
      }

      const data = await getQuotaStatus(token);
      setQuota(data);
    } catch (err) {
      console.error('Error fetching quota:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchQuota();
    trackEvent({ name: 'billing_page_viewed' });
  }, [effectiveIsSignedIn]);

  const handleWaitlistSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    // TODO: Send to waitlist API endpoint
    console.log('Waitlist signup:', email);
    trackEvent({ name: 'pro_waitlist_signup', data: { source: 'billing_page' } });
    setSubmitted(true);
  };

  const formatResetDate = (dateStr: string) => {
    const date = new Date(dateStr);
    return date.toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' });
  };

  return (
    <div className="flex h-screen overflow-hidden" style={{ backgroundColor: 'var(--background)' }}>
      <Sidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} />

      {/* Overlay for mobile */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 bg-black/50 z-40 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      <main className="flex-1 overflow-auto">
        {/* Header */}
        <header className="sticky top-0 z-30 border-b bg-white px-6 py-4" style={{ borderColor: 'var(--border)' }}>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <button
                onClick={() => setSidebarOpen(!sidebarOpen)}
                className="lg:hidden p-2 hover:bg-gray-100 rounded-lg"
              >
                <Menu className="w-5 h-5" />
              </button>
              <div>
                <h1 className="text-2xl font-semibold" style={{ color: 'var(--warm-charcoal)' }}>
                  Billing & Subscription
                </h1>
                <p className="text-sm" style={{ color: 'var(--warm-gray)' }}>
                  Manage your quota and subscription tier
                </p>
              </div>
            </div>
            {isDevelopmentMode ? (
              <div style={{
                fontSize: '0.75em',
                color: 'var(--warm-gray)',
                padding: '0.5rem',
                backgroundColor: 'var(--soft-cream)',
                borderRadius: 'var(--radius)',
                border: '1px solid var(--border)'
              }}>
                DEV MODE
              </div>
            ) : (
              isSignedIn && <UserMenu />
            )}
          </div>
        </header>

        {/* Content */}
        <div className="p-6" style={{ backgroundColor: 'var(--soft-cream)' }}>
          {loading ? (
            <div className="text-center py-12">
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 mx-auto" style={{ borderColor: 'var(--terracotta)' }}></div>
              <p className="mt-4" style={{ color: 'var(--warm-gray)' }}>Loading billing information...</p>
            </div>
          ) : (
            <div className="space-y-6 max-w-5xl mx-auto">
            {/* Current tier */}
            <div
              className="p-6 rounded-lg"
              style={{ backgroundColor: 'var(--card)', border: '1px solid var(--border)' }}
            >
              <div className="flex items-start justify-between mb-4">
                <div>
                  <h2 style={{ fontSize: '1.5rem', fontWeight: 600, color: 'var(--warm-charcoal)', marginBottom: '0.25rem' }}>
                    {quota?.is_beta ? 'Beta Tier' : 'Free Tier'}
                  </h2>
                  <p style={{ fontSize: '0.925em', color: 'var(--warm-gray)' }}>
                    Your current subscription
                  </p>
                </div>
                <div
                  className="px-3 py-1 rounded-full"
                  style={{
                    backgroundColor: 'var(--sage-green)',
                    color: 'white',
                    fontSize: '0.75em',
                    fontWeight: 600,
                    textTransform: 'uppercase',
                    letterSpacing: '0.05em'
                  }}
                >
                  Active
                </div>
              </div>

              {/* Features */}
              <div className="space-y-2 mb-6">
                {[
                  quota?.is_beta ? '200 pages/month OCR transcription' : '30 pages/month OCR transcription',
                  'Unlimited notebook syncing',
                  'PDF viewing in dashboard',
                  'Basic integrations (up to quota)'
                ].map((feature, index) => (
                  <div key={index} className="flex items-start gap-3">
                    <CheckCircle className="w-4 h-4 flex-shrink-0 mt-0.5" style={{ color: 'var(--sage-green)' }} />
                    <span style={{ fontSize: '0.925em', color: 'var(--warm-charcoal)' }}>{feature}</span>
                  </div>
                ))}
              </div>

              {/* Quota display */}
              {quota && (
                <div className="border-t pt-4" style={{ borderColor: 'var(--border)' }}>
                  <QuotaDisplay variant="full" />
                </div>
              )}
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

              <h2 style={{ fontSize: '1.5rem', fontWeight: 600, color: 'var(--warm-charcoal)', marginBottom: '0.25rem' }}>
                Pro Tier
              </h2>
              <p style={{ fontSize: '1.125rem', color: 'var(--terracotta)', fontWeight: 500, marginBottom: '1.5rem' }}>
                Launching February 2026
              </p>

              {/* Features */}
              <div className="space-y-3 mb-6">
                {[
                  '500 pages/month OCR transcription (16x more!)',
                  'All integrations enabled',
                  'Priority processing',
                  'Email support',
                  'Advanced features'
                ].map((feature, index) => (
                  <div key={index} className="flex items-start gap-3">
                    <CheckCircle className="w-5 h-5 flex-shrink-0" style={{ color: 'var(--sage-green)' }} />
                    <span style={{ fontSize: '0.925em', color: 'var(--warm-charcoal)' }}>{feature}</span>
                  </div>
                ))}
              </div>

              {/* Pricing */}
              <div
                className="p-4 rounded-lg mb-4"
                style={{ backgroundColor: 'var(--soft-cream)' }}
              >
                <div style={{ fontSize: '0.75em', color: 'var(--warm-gray)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '0.25rem' }}>
                  Expected Pricing
                </div>
                <div style={{ fontSize: '2.5rem', fontWeight: 600, color: 'var(--warm-charcoal)' }}>
                  $9<span style={{ fontSize: '1.25rem', fontWeight: 400, color: 'var(--warm-gray)' }}>/month</span>
                </div>
                <p style={{ fontSize: '0.875em', color: 'var(--warm-gray)', marginTop: '0.5rem', marginBottom: 0 }}>
                  ~$0.018 per page • Cancel anytime
                </p>
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
                      className="flex-1 px-4 py-2.5 rounded-lg"
                      style={{
                        border: '1px solid var(--border)',
                        fontSize: '0.925em',
                        backgroundColor: 'var(--card)',
                        color: 'var(--foreground)'
                      }}
                    />
                    <button
                      type="submit"
                      className="px-6 py-2.5 rounded-lg transition-colors font-semibold"
                      style={{
                        backgroundColor: 'var(--primary)',
                        color: 'var(--primary-foreground)',
                        fontSize: '0.925em'
                      }}
                    >
                      Join Waitlist
                    </button>
                  </div>
                  <p style={{ fontSize: '0.75em', color: 'var(--warm-gray)', marginTop: '0.5rem', marginBottom: 0 }}>
                    Be the first to know when Pro tier launches
                  </p>
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

            {/* Beta note */}
            {quota?.is_beta && (
              <div
                className="p-6 rounded-lg"
                style={{ backgroundColor: 'var(--soft-cream)', border: '1px solid var(--border)' }}
              >
                <div className="flex items-start gap-3">
                  <CheckCircle className="w-5 h-5 flex-shrink-0 mt-0.5" style={{ color: 'var(--sage-green)' }} />
                  <div>
                    <h3 style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--warm-charcoal)', marginBottom: '0.5rem' }}>
                      Beta Program
                    </h3>
                    <p style={{ fontSize: '0.925em', color: 'var(--warm-gray)' }}>
                      You're part of our beta program — enjoy 200 pages/month as a thank you for being an early adopter!
                    </p>
                  </div>
                </div>
              </div>
            )}

            {/* Quota reset info */}
            {quota && (
              <div
                className="p-4 rounded-lg text-center"
                style={{ backgroundColor: 'var(--card)', border: '1px solid var(--border)' }}
              >
                <p style={{ fontSize: '0.875em', color: 'var(--warm-gray)' }}>
                  Your quota will reset on{' '}
                  <strong style={{ color: 'var(--warm-charcoal)' }}>
                    {formatResetDate(quota.reset_at)}
                  </strong>
                </p>
              </div>
            )}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
