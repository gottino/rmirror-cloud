'use client';

import { useAuth, UserButton } from '@clerk/nextjs';
import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import ReactMarkdown from 'react-markdown';
import { getNotebook, type NotebookWithPages } from '@/lib/api';

export default function NotebookPage() {
  const params = useParams();
  const router = useRouter();
  const { getToken, isSignedIn } = useAuth();
  const [notebook, setNotebook] = useState<NotebookWithPages | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [copiedPageId, setCopiedPageId] = useState<number | null>(null);

  // Development mode bypass
  const isDevelopmentMode = process.env.NEXT_PUBLIC_DEV_MODE === 'true';
  const effectiveIsSignedIn = isDevelopmentMode || isSignedIn;

  useEffect(() => {
    if (!effectiveIsSignedIn) {
      router.push('/');
      return;
    }

    const fetchNotebook = async () => {
      try {
        // In dev mode, use a mock token that bypasses Clerk
        const token = isDevelopmentMode ? 'dev-mode-bypass' : await getToken();
        if (!token) {
          throw new Error('Failed to get authentication token');
        }

        const id = Number(params.id);
        if (isNaN(id)) {
          throw new Error('Invalid notebook ID');
        }

        const data = await getNotebook(id, token);
        setNotebook(data);
      } catch (err) {
        console.error('Error fetching notebook:', err);
        setError(err instanceof Error ? err.message : 'Failed to fetch notebook');
      } finally {
        setLoading(false);
      }
    };

    fetchNotebook();
  }, [params.id, effectiveIsSignedIn, getToken, router, isDevelopmentMode]);

  // Header component that's always visible
  const Header = () => (
    <header className="bg-white shadow-sm sticky top-0 z-50" style={{ borderBottom: '1px solid var(--border)' }}>
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
        <div className="flex items-center justify-between">
          <Link href="/" className="flex items-center space-x-3 hover:opacity-80 transition-opacity">
            <h1 style={{ fontSize: '1.5rem', fontWeight: 600, color: 'var(--warm-charcoal)', margin: 0 }}>rMirror</h1>
          </Link>
          <div className="flex items-center space-x-4">
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
              isSignedIn && <UserButton afterSignOutUrl="/" />
            )}
          </div>
        </div>
      </div>
    </header>
  );

  if (loading) {
    return (
      <>
        <Header />
        <div className="min-h-screen flex items-center justify-center" style={{ backgroundColor: 'var(--background)' }}>
          <div className="text-center">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 mx-auto" style={{ borderColor: 'var(--terracotta)' }}></div>
            <p className="mt-4" style={{ color: 'var(--warm-gray)' }}>Loading notebook...</p>
          </div>
        </div>
      </>
    );
  }

  if (error || !notebook) {
    return (
      <>
        <Header />
        <div className="min-h-screen flex items-center justify-center px-4" style={{ backgroundColor: 'var(--background)' }}>
          <div className="text-center max-w-md">
            <div style={{ color: 'var(--destructive)', fontSize: '3rem', marginBottom: '1rem' }}>✗</div>
            <h2 style={{ fontSize: '1.5rem', fontWeight: 600, marginBottom: '0.5rem' }}>Error</h2>
            <p style={{ color: 'var(--warm-gray)', marginBottom: '1.5rem' }}>{error || 'Notebook not found'}</p>
            <Link
              href="/"
              className="inline-block px-6 py-2 rounded-lg transition-colors"
              style={{
                backgroundColor: 'var(--primary)',
                color: 'var(--primary-foreground)'
              }}
            >
              ← Back to notebooks
            </Link>
          </div>
        </div>
      </>
    );
  }

  // Sort pages in reverse order (highest page number first)
  const sortedPages = [...notebook.pages].sort((a, b) => b.page_number - a.page_number);

  return (
    <>
      <Header />
      <div className="min-h-screen" style={{ backgroundColor: 'var(--background)' }}>
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
          {/* Back link and notebook header */}
          <div className="mb-8">
            <Link
              href="/"
              className="inline-flex items-center mb-4 hover:opacity-80 transition-opacity"
              style={{ color: 'var(--terracotta)', fontSize: '0.925em', fontWeight: 500 }}
            >
              ← Back to notebooks
            </Link>

          <h1 style={{ fontSize: '2rem', fontWeight: 600, color: 'var(--warm-charcoal)', marginBottom: '0.5rem' }}>
            {notebook.visible_name || notebook.title || 'Untitled'}
          </h1>

          <div className="flex items-center gap-4" style={{ fontSize: '0.875em', color: 'var(--warm-gray)' }}>
            {notebook.author && (
              <span>
                <span style={{ fontWeight: 500 }}>Author:</span> {notebook.author}
              </span>
            )}
            <span>
              <span style={{ fontWeight: 500 }}>Type:</span> {notebook.document_type.toUpperCase()}
            </span>
            <span>
              <span style={{ fontWeight: 500 }}>Pages:</span> {notebook.pages.length}
            </span>
          </div>
        </div>

        {/* Pages */}
        {sortedPages.length === 0 ? (
          <div className="text-center py-12 rounded-lg" style={{ backgroundColor: 'var(--card)', border: '1px solid var(--border)' }}>
            <h3 style={{ fontSize: '1.25rem', fontWeight: 600, marginBottom: '0.5rem' }}>
              No pages found
            </h3>
            <p style={{ color: 'var(--warm-gray)' }}>
              This notebook doesn't have any pages yet.
            </p>
          </div>
        ) : (
          <div className="space-y-6">
            {sortedPages.map((page) => {
              const handleCopy = async () => {
                if (page.ocr_text) {
                  await navigator.clipboard.writeText(page.ocr_text);
                  setCopiedPageId(page.id);
                  setTimeout(() => setCopiedPageId(null), 2000);
                }
              };

              return (
                <div
                  key={page.id}
                  className="rounded-lg p-6 relative"
                  style={{ backgroundColor: 'var(--card)', border: '1px solid var(--border)' }}
                >
                  <div className="flex items-center justify-between mb-4">
                    <h3 style={{ fontSize: '1.125rem', fontWeight: 600, color: 'var(--warm-charcoal)' }}>
                      Page {page.page_number}
                    </h3>

                    <div className="flex items-center gap-3">
                      {page.ocr_status === 'completed' && page.ocr_text && (
                        <button
                          onClick={handleCopy}
                          className="p-2 rounded transition-colors hover:bg-[var(--soft-cream)]"
                          style={{ color: 'var(--warm-gray)' }}
                          title="Copy markdown"
                        >
                          {copiedPageId === page.id ? (
                            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" style={{ color: 'var(--sage-green)' }}>
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                            </svg>
                          ) : (
                            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                            </svg>
                          )}
                        </button>
                      )}

                      <span
                        className="px-3 py-1 rounded-full"
                        style={{
                          fontSize: '0.875em',
                          fontWeight: 500,
                          backgroundColor: page.ocr_status === 'completed'
                            ? 'rgba(122, 156, 137, 0.15)'
                            : page.ocr_status === 'processing'
                            ? 'rgba(212, 165, 116, 0.15)'
                            : page.ocr_status === 'failed'
                            ? 'rgba(220, 38, 38, 0.15)'
                            : 'var(--soft-cream)',
                          color: page.ocr_status === 'completed'
                            ? 'var(--sage-green)'
                            : page.ocr_status === 'processing'
                            ? 'var(--amber-gold)'
                            : page.ocr_status === 'failed'
                            ? 'var(--destructive)'
                            : 'var(--warm-gray)'
                        }}
                      >
                        {page.ocr_status}
                      </span>
                    </div>
                  </div>

                  {page.ocr_status === 'completed' && page.ocr_text ? (
                    <div className="prose prose-sm sm:prose max-w-none prose-headings:font-semibold prose-h1:text-2xl prose-h2:text-xl prose-h3:text-lg prose-p:text-[var(--warm-charcoal)] prose-ul:text-[var(--warm-charcoal)] prose-ol:text-[var(--warm-charcoal)] prose-li:text-[var(--warm-charcoal)] prose-strong:text-[var(--warm-charcoal)] prose-a:text-[var(--terracotta)] hover:prose-a:opacity-80">
                      <ReactMarkdown>{page.ocr_text}</ReactMarkdown>
                    </div>
                  ) : page.ocr_status === 'failed' && page.ocr_error ? (
                    <div className="rounded p-4" style={{ backgroundColor: 'rgba(220, 38, 38, 0.1)', border: '1px solid rgba(220, 38, 38, 0.2)' }}>
                      <p style={{ color: 'var(--destructive)', fontWeight: 500, marginBottom: '0.5rem' }}>OCR Failed</p>
                      <p style={{ color: 'var(--destructive)', fontSize: '0.875em', opacity: 0.8 }}>{page.ocr_error}</p>
                    </div>
                  ) : page.ocr_status === 'processing' ? (
                    <div className="rounded p-4 flex items-center" style={{ backgroundColor: 'rgba(212, 165, 116, 0.1)', border: '1px solid rgba(212, 165, 116, 0.2)' }}>
                      <div className="animate-spin rounded-full h-5 w-5 border-b-2 mr-3" style={{ borderColor: 'var(--amber-gold)' }}></div>
                      <p style={{ color: 'var(--amber-gold)', fontWeight: 500 }}>Processing OCR...</p>
                    </div>
                  ) : (
                    <div className="rounded p-4" style={{ backgroundColor: 'var(--soft-cream)', border: '1px solid var(--border)' }}>
                      <p style={{ color: 'var(--warm-gray)' }}>OCR pending</p>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
        </div>
      </div>
    </>
  );
}
