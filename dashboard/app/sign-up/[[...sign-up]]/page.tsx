'use client';

import { SignUp } from '@clerk/nextjs';
import { useSearchParams } from 'next/navigation';
import { useState, useEffect, Suspense } from 'react';
import Link from 'next/link';
import { validateInviteToken } from '@/lib/api';

export default function Page() {
  return (
    <Suspense>
      <SignUpGate />
    </Suspense>
  );
}

function SignUpGate() {
  const searchParams = useSearchParams();
  const inviteToken = searchParams.get('invite');

  const [loading, setLoading] = useState(true);
  const [valid, setValid] = useState(false);
  const [invitedEmail, setInvitedEmail] = useState<string | null>(null);
  const [reason, setReason] = useState<string | null>(null);

  // Waitlist form state
  const [email, setEmail] = useState('');
  const [name, setName] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  useEffect(() => {
    if (!inviteToken) {
      setLoading(false);
      return;
    }

    validateInviteToken(inviteToken).then((result) => {
      setValid(result.valid);
      setInvitedEmail(result.email || null);
      setReason(result.reason || null);
      setLoading(false);
    }).catch(() => {
      setReason('Failed to validate invite');
      setLoading(false);
    });
  }, [inviteToken]);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center" style={{ background: 'var(--background)' }}>
        <div style={{ color: 'var(--warm-gray)', fontSize: '1rem' }}>Validating invite...</div>
      </div>
    );
  }

  // Valid invite: show Clerk SignUp
  if (inviteToken && valid) {
    return (
      <div className="min-h-screen flex items-center justify-center" style={{ background: 'var(--background)' }}>
        <SignUp
          signInUrl="/sign-in"
          initialValues={invitedEmail ? { emailAddress: invitedEmail } : undefined}
        />
      </div>
    );
  }

  // No token or invalid token: show gated page
  const handleWaitlistSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);

    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/v1/waitlist`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, name: name || undefined }),
      });

      if (response.ok) {
        setSubmitted(true);
      }
    } catch {
      // Silent fail
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center" style={{ background: 'var(--background)' }}>
      <div
        className="w-full max-w-md mx-4 p-8 rounded-xl"
        style={{ background: 'var(--card)', boxShadow: 'var(--shadow-md)' }}
      >
        <div className="text-center mb-6">
          <h1
            className="text-2xl font-bold mb-2"
            style={{ color: 'var(--warm-charcoal)' }}
          >
            Invitation Required
          </h1>
          <p style={{ color: 'var(--warm-gray)', fontSize: '0.95rem' }}>
            rMirror is currently in closed beta. You need an invitation to sign up.
          </p>
        </div>

        {/* Show specific error if token was provided */}
        {inviteToken && reason && (
          <div
            className="mb-6 p-3 rounded-lg text-sm"
            style={{
              background: 'var(--soft-cream)',
              border: '1px solid var(--border)',
              color: 'var(--warm-charcoal)',
            }}
          >
            {reason}
          </div>
        )}

        {/* Waitlist form */}
        {!submitted ? (
          <form onSubmit={handleWaitlistSubmit} className="space-y-4">
            <p
              className="text-sm mb-4"
              style={{ color: 'var(--warm-gray)' }}
            >
              Request access and we'll send you an invite when a spot opens up.
            </p>
            <div>
              <input
                type="text"
                placeholder="Name (optional)"
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="w-full px-4 py-2.5 rounded-lg text-sm"
                style={{
                  background: 'var(--background)',
                  border: '1px solid var(--border)',
                  color: 'var(--warm-charcoal)',
                }}
              />
            </div>
            <div>
              <input
                type="email"
                placeholder="Email address"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                className="w-full px-4 py-2.5 rounded-lg text-sm"
                style={{
                  background: 'var(--background)',
                  border: '1px solid var(--border)',
                  color: 'var(--warm-charcoal)',
                }}
              />
            </div>
            <button
              type="submit"
              disabled={submitting || !email}
              className="w-full py-2.5 rounded-lg font-semibold text-sm transition-all"
              style={{
                background: 'var(--terracotta)',
                color: 'white',
                opacity: submitting || !email ? 0.6 : 1,
              }}
            >
              {submitting ? 'Requesting...' : 'Request Early Access'}
            </button>
          </form>
        ) : (
          <div
            className="p-4 rounded-lg text-center"
            style={{ background: 'var(--soft-cream)', border: '1px solid var(--sage-green)' }}
          >
            <p className="font-semibold mb-1" style={{ color: 'var(--warm-charcoal)' }}>
              You're on the list!
            </p>
            <p className="text-sm" style={{ color: 'var(--warm-gray)' }}>
              We'll email you when your invite is ready.
            </p>
          </div>
        )}

        <div className="mt-6 text-center">
          <p className="text-sm" style={{ color: 'var(--warm-gray)' }}>
            Already have an account?{' '}
            <Link
              href="/sign-in"
              style={{ color: 'var(--terracotta)', fontWeight: 500 }}
            >
              Sign in
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
