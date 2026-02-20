import Link from 'next/link';
import Image from 'next/image';

export default function LegalLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div
      className="min-h-screen flex flex-col"
      style={{ background: 'var(--background)' }}
    >
      {/* Header */}
      <header
        className="border-b"
        style={{ borderColor: 'var(--border)', background: 'var(--card)' }}
      >
        <div className="max-w-3xl mx-auto px-6 py-4 flex items-center justify-between">
          <Link href="/" className="flex items-center gap-2">
            <Image src="/landing-logo.png" alt="rMirror" width={28} height={28} />
            <span
              className="font-semibold"
              style={{ color: 'var(--warm-charcoal)', fontSize: '1.1rem' }}
            >
              rMirror Cloud
            </span>
          </Link>
          <nav className="flex gap-6" style={{ fontSize: '0.875rem' }}>
            <Link
              href="/legal/terms"
              className="transition-colors hover:opacity-70"
              style={{ color: 'var(--warm-gray)' }}
            >
              Terms
            </Link>
            <Link
              href="/legal/privacy"
              className="transition-colors hover:opacity-70"
              style={{ color: 'var(--warm-gray)' }}
            >
              Privacy
            </Link>
          </nav>
        </div>
      </header>

      {/* Content */}
      <main className="flex-1">
        <div className="max-w-3xl mx-auto px-6 py-12">
          {children}
        </div>
      </main>

      {/* Footer */}
      <footer
        className="border-t py-8"
        style={{ borderColor: 'var(--border)', background: 'var(--soft-cream)' }}
      >
        <div className="max-w-3xl mx-auto px-6 flex flex-col sm:flex-row justify-between items-center gap-4">
          <p className="text-sm" style={{ color: 'var(--warm-gray)' }}>
            &copy; 2026 rMirror Cloud
          </p>
          <div className="flex gap-6 text-sm">
            <Link
              href="/legal/terms"
              className="transition-colors hover:opacity-70"
              style={{ color: 'var(--warm-gray)' }}
            >
              Terms of Service
            </Link>
            <Link
              href="/legal/privacy"
              className="transition-colors hover:opacity-70"
              style={{ color: 'var(--warm-gray)' }}
            >
              Privacy Policy
            </Link>
            <a
              href="mailto:support@rmirror.io"
              className="transition-colors hover:opacity-70"
              style={{ color: 'var(--warm-gray)' }}
            >
              Contact
            </a>
          </div>
        </div>
      </footer>
    </div>
  );
}
