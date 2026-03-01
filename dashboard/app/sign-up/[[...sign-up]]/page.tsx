'use client';

import { SignUp } from '@clerk/nextjs';
import Link from 'next/link';

export default function SignUpPage() {
  return (
    <div className="min-h-screen flex items-center justify-center" style={{ background: 'var(--cream)' }}>
      <div className="text-center">
        <div className="mb-8">
          <h1 className="text-3xl font-bold mb-2" style={{ color: 'var(--warm-charcoal)', fontFamily: 'var(--font-display)' }}>
            Join rMirror
          </h1>
          <div className="inline-block px-2 py-0.5 rounded text-xs font-medium mb-2" style={{ background: 'var(--terracotta)', color: 'white' }}>
            BETA
          </div>
          <p style={{ color: 'var(--warm-gray)' }}>
            Your reMarkable notebooks, searchable everywhere
          </p>
        </div>
        <SignUp
          appearance={{
            elements: {
              rootBox: 'mx-auto',
              card: 'shadow-lg',
            },
          }}
        />
        <p className="mt-6 text-center text-sm max-w-sm mx-auto" style={{ color: 'var(--warm-gray)' }}>
          By creating an account, you agree to our{' '}
          <Link href="/legal/terms" className="underline hover:opacity-80" style={{ color: 'var(--terracotta)' }}>
            Terms of Service
          </Link>{' '}
          and{' '}
          <Link href="/legal/privacy" className="underline hover:opacity-80" style={{ color: 'var(--terracotta)' }}>
            Privacy Policy
          </Link>.
        </p>
      </div>
    </div>
  );
}
