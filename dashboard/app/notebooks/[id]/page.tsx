'use client';

import { useAuth, UserButton } from '@clerk/nextjs';
import { Suspense, useEffect, useState, useRef, useCallback } from 'react';
import { useParams, useRouter, useSearchParams } from 'next/navigation';
import Link from 'next/link';
import ReactMarkdown from 'react-markdown';
import { ChevronRight, ChevronDown, Download, FileText, FileDown, Calendar, Clock, CloudUpload, Menu, Search, X, Loader2 } from 'lucide-react';
import { getNotebook, getQuotaStatus, searchNotebooks, QuotaExceededError, type NotebookWithPages, type Page, type QuotaStatus, type SearchResponse } from '@/lib/api';
import Sidebar from '@/components/Sidebar';
import { QuotaDisplay } from '@/components/QuotaDisplay';
import { QuotaExceededModal } from '@/components/QuotaExceededModal';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'https://rmirror.io/api/v1';

interface PageCardProps {
  page: Page;
  token: string;
  copiedPageId: number | null;
  setCopiedPageId: (id: number | null) => void;
  quota: QuotaStatus | null;
  isTargetPage?: boolean;
  cardRef?: (el: HTMLDivElement | null) => void;
}

function PageCard({ page, token, copiedPageId, setCopiedPageId, quota, isTargetPage, cardRef }: PageCardProps) {
  const [showPdf, setShowPdf] = useState(false);
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  const [pdfBlob, setPdfBlob] = useState<string | null>(null);
  const [loadingPdf, setLoadingPdf] = useState(false);
  const hasPdf = !!page.pdf_s3_key;

  const handleCopy = async () => {
    if (page.ocr_text) {
      await navigator.clipboard.writeText(page.ocr_text);
      setCopiedPageId(page.id);
      setTimeout(() => setCopiedPageId(null), 2000);
    }
  };

  const handleTogglePdf = async () => {
    if (!hasPdf) return;

    if (!showPdf && !pdfBlob) {
      // Fetch PDF with authentication
      setLoadingPdf(true);
      try {
        const url = `${API_URL}/pages/${page.id}/pdf`;
        const response = await fetch(url, {
          headers: {
            'Authorization': `Bearer ${token}`,
          },
        });

        if (!response.ok) {
          throw new Error('Failed to load PDF');
        }

        const blob = await response.blob();
        const blobUrl = URL.createObjectURL(blob);
        setPdfBlob(blobUrl);
      } catch (error) {
        console.error('Error loading PDF:', error);
      } finally {
        setLoadingPdf(false);
      }
    }

    setShowPdf(!showPdf);
  };

  return (
    <div
      ref={cardRef}
      className="relative transition-all duration-500 ease-in-out"
      style={{
        perspective: '1000px',
        marginBottom: showPdf ? '1.5rem' : '0',
      }}
    >
      {/* Stack indicator - shows when PDF is available */}
      {hasPdf && !showPdf && (
        <>
          <div
            className="absolute inset-0 rounded-lg"
            style={{
              backgroundColor: 'var(--card)',
              border: '1px solid var(--border)',
              transform: 'translateY(-4px) translateX(4px)',
              zIndex: -2,
              opacity: 0.4,
            }}
          />
          <div
            className="absolute inset-0 rounded-lg"
            style={{
              backgroundColor: 'var(--card)',
              border: '1px solid var(--border)',
              transform: 'translateY(-2px) translateX(2px)',
              zIndex: -1,
              opacity: 0.7,
            }}
          />
        </>
      )}

      {/* Main card with flip animation */}
      <div
        className={`relative rounded-lg transition-all duration-500 ease-in-out ${isTargetPage ? 'ring-2 ring-[var(--terracotta)]' : ''}`}
        style={{
          backgroundColor: 'var(--card)',
          border: isTargetPage ? '1px solid var(--terracotta)' : '1px solid var(--border)',
          transformStyle: 'preserve-3d',
          transform: showPdf ? 'rotateY(180deg)' : 'rotateY(0deg)',
          height: showPdf ? '800px' : 'auto',
        }}
      >
        {/* Front: Text content */}
        <div
          className="rounded-lg"
          style={{
            backfaceVisibility: 'hidden',
            backgroundColor: 'var(--card)',
            position: showPdf ? 'absolute' : 'relative',
            inset: showPdf ? '0' : 'auto',
            overflow: showPdf ? 'auto' : 'visible',
          }}
        >
          <div className="p-6">
            <div className="flex items-center justify-between mb-4">
            <h3 style={{ fontSize: '1.125rem', fontWeight: 600, color: 'var(--warm-charcoal)' }}>
              Page {page.page_number}
            </h3>

            <div className="flex items-center gap-3">
              {hasPdf && (
                <button
                  onClick={handleTogglePdf}
                  className="p-2 rounded transition-colors hover:bg-[var(--soft-cream)]"
                  style={{ color: 'var(--terracotta)' }}
                  title="View PDF"
                >
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
                  </svg>
                </button>
              )}

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
                    : page.ocr_status === 'pending_quota'
                    ? 'rgba(212, 165, 116, 0.15)'
                    : page.ocr_status === 'not_synced'
                    ? 'rgba(156, 163, 175, 0.15)'
                    : 'var(--soft-cream)',
                  color: page.ocr_status === 'completed'
                    ? 'var(--sage-green)'
                    : page.ocr_status === 'processing'
                    ? 'var(--amber-gold)'
                    : page.ocr_status === 'failed'
                    ? 'var(--destructive)'
                    : page.ocr_status === 'pending_quota'
                    ? 'var(--amber-gold)'
                    : page.ocr_status === 'not_synced'
                    ? 'var(--warm-gray)'
                    : 'var(--warm-gray)'
                }}
              >
                {page.ocr_status === 'pending_quota' ? 'Awaiting Quota' : page.ocr_status === 'not_synced' ? 'Not Synced' : page.ocr_status}
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
          ) : page.ocr_status === 'pending_quota' ? (
            <div className="rounded p-6 text-center" style={{ backgroundColor: 'rgba(212, 165, 116, 0.1)', border: '1px solid rgba(212, 165, 116, 0.2)' }}>
              <p style={{ color: 'var(--amber-gold)', fontWeight: 500, marginBottom: '0.75rem', fontSize: '1.125em' }}>OCR Pending - Quota Exhausted</p>
              <p style={{ color: 'var(--warm-charcoal)', fontSize: '0.875em', marginBottom: '1rem', opacity: 0.9 }}>
                Your monthly OCR quota has been reached. This page will be automatically processed when your quota resets
                {quota?.reset_at && (
                  <> on <strong>{new Date(quota.reset_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}</strong></>
                )}, or you can upgrade to Pro for more capacity.
              </p>
              <a
                href="/billing"
                className="inline-block px-4 py-2 rounded-lg transition-colors font-medium"
                style={{
                  backgroundColor: 'var(--terracotta)',
                  color: 'white',
                  fontSize: '0.875em'
                }}
              >
                Upgrade to Pro
              </a>
            </div>
          ) : page.ocr_status === 'not_synced' ? (
            <div className="rounded p-6 text-center" style={{ backgroundColor: 'rgba(156, 163, 175, 0.1)', border: '1px solid rgba(156, 163, 175, 0.2)' }}>
              <div className="flex items-center justify-center mb-3">
                <svg className="w-8 h-8" style={{ color: 'var(--warm-gray)' }} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
                </svg>
              </div>
              <p style={{ color: 'var(--warm-gray)', fontWeight: 500, marginBottom: '0.5rem', fontSize: '1em' }}>Not synced yet</p>
              <p style={{ color: 'var(--warm-gray)', fontSize: '0.875em', opacity: 0.8 }}>
                This page is waiting to be uploaded from your reMarkable device.
              </p>
            </div>
          ) : (
            <div className="rounded p-4" style={{ backgroundColor: 'var(--soft-cream)', border: '1px solid var(--border)' }}>
              <p style={{ color: 'var(--warm-gray)' }}>OCR pending</p>
            </div>
          )}
          </div>
        </div>

        {/* Back: PDF viewer */}
        {hasPdf && (
          <div
            className="absolute inset-0 p-6 rounded-lg flex flex-col"
            style={{
              backfaceVisibility: 'hidden',
              transform: 'rotateY(180deg)',
              backgroundColor: 'var(--card)',
            }}
          >
            <div className="flex items-center justify-between mb-4">
              <h3 style={{ fontSize: '1.125rem', fontWeight: 600, color: 'var(--warm-charcoal)' }}>
                Page {page.page_number} - PDF
              </h3>

              <button
                onClick={handleTogglePdf}
                className="p-2 rounded transition-colors hover:bg-[var(--soft-cream)]"
                style={{ color: 'var(--terracotta)' }}
                title="Back to text"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            {loadingPdf ? (
              <div className="flex-1 flex items-center justify-center">
                <div className="animate-spin rounded-full h-12 w-12 border-b-2" style={{ borderColor: 'var(--terracotta)' }}></div>
              </div>
            ) : pdfBlob ? (
              <iframe
                src={pdfBlob}
                className="w-full rounded"
                style={{ border: '1px solid var(--border)', height: 'calc(100% - 4rem)' }}
                title={`Page ${page.page_number} PDF`}
              />
            ) : (
              <div className="flex-1 flex items-center justify-center">
                <p style={{ color: 'var(--warm-gray)' }}>Click to load PDF</p>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// Sync progress component shows progress when pages are being synced
interface SyncProgressProps {
  pages: Page[];
}

function SyncProgress({ pages }: SyncProgressProps) {
  if (pages.length === 0) return null;

  const notSyncedCount = pages.filter(p => p.ocr_status === 'not_synced').length;
  const syncedCount = pages.filter(p => p.ocr_status !== 'not_synced').length;
  const totalPages = pages.length;
  const progressPercent = totalPages > 0 ? Math.round((syncedCount / totalPages) * 100) : 0;

  // Only show if there are not_synced pages
  if (notSyncedCount === 0) return null;

  return (
    <div className="rounded-lg p-4 mb-6" style={{ backgroundColor: 'rgba(156, 163, 175, 0.1)', border: '1px solid rgba(156, 163, 175, 0.2)' }}>
      <div className="flex items-center gap-3 mb-3">
        <CloudUpload className="w-5 h-5" style={{ color: 'var(--warm-gray)' }} />
        <span style={{ fontSize: '0.925em', fontWeight: 500, color: 'var(--warm-charcoal)' }}>
          {notSyncedCount} {notSyncedCount === 1 ? 'page' : 'pages'} awaiting upload from your reMarkable
        </span>
      </div>
      <div className="flex items-center gap-4">
        {/* Progress bar */}
        <div className="flex-1 h-2 rounded-full overflow-hidden" style={{ backgroundColor: 'rgba(156, 163, 175, 0.2)' }}>
          <div
            className="h-full rounded-full transition-all duration-500"
            style={{
              width: `${progressPercent}%`,
              backgroundColor: progressPercent === 100 ? 'var(--sage-green)' : 'var(--terracotta)'
            }}
          />
        </div>
        {/* Progress text */}
        <span style={{ fontSize: '0.875em', color: 'var(--warm-gray)', minWidth: '100px', textAlign: 'right' }}>
          {syncedCount} / {totalPages} uploaded
        </span>
      </div>
    </div>
  );
}

function NotebookPageContent() {
  const params = useParams();
  const router = useRouter();
  const searchParams = useSearchParams();
  const { getToken, isSignedIn } = useAuth();
  const [notebook, setNotebook] = useState<NotebookWithPages | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [copiedPageId, setCopiedPageId] = useState<number | null>(null);
  const [authToken, setAuthToken] = useState<string>('');
  const [quota, setQuota] = useState<QuotaStatus | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [exportMenuOpen, setExportMenuOpen] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [quotaModalOpen, setQuotaModalOpen] = useState(false);
  const [quotaModalData, setQuotaModalData] = useState<QuotaStatus | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);

  // Target page from URL query param (for search result navigation)
  const targetPage = searchParams.get('page');
  const pageRefs = useRef<Map<number, HTMLDivElement>>(new Map());

  // In-notebook search state
  const [notebookSearchQuery, setNotebookSearchQuery] = useState('');
  const [notebookSearchResults, setNotebookSearchResults] = useState<SearchResponse | null>(null);
  const [notebookSearchLoading, setNotebookSearchLoading] = useState(false);
  const [isNotebookSearchMode, setIsNotebookSearchMode] = useState(false);
  const searchDebounceTimer = useRef<NodeJS.Timeout>();

  // Development mode: use JWT token from localStorage
  const isDevelopmentMode = process.env.NEXT_PUBLIC_DEV_MODE === 'true';
  const effectiveIsSignedIn = isDevelopmentMode || isSignedIn;

  useEffect(() => {
    if (!effectiveIsSignedIn) {
      router.push('/');
      return;
    }

    const fetchNotebook = async () => {
      try {
        // In dev mode, get JWT token from env var or localStorage
        const token = isDevelopmentMode
          ? process.env.NEXT_PUBLIC_DEV_AUTH_TOKEN || localStorage.getItem('dev_auth_token') || ''
          : await getToken();

        if (!token) {
          throw new Error('Failed to get authentication token');
        }

        // Store token for PDF fetching
        setAuthToken(token);

        const id = Number(params.id);
        if (isNaN(id)) {
          throw new Error('Invalid notebook ID');
        }

        const data = await getNotebook(id, token);
        setNotebook(data);

        // Fetch quota data
        try {
          const quotaData = await getQuotaStatus(token);
          setQuota(quotaData);
        } catch (quotaErr) {
          console.error('Error fetching quota:', quotaErr);
        }
      } catch (err) {
        console.error('Error fetching notebook:', err);
        setError(err instanceof Error ? err.message : 'Failed to fetch notebook');
      } finally {
        setLoading(false);
      }
    };

    fetchNotebook();
  }, [params.id, effectiveIsSignedIn, getToken, router, isDevelopmentMode]);

  // Scroll to target page when navigating from search results
  useEffect(() => {
    if (notebook && targetPage && !loading) {
      const pageNum = parseInt(targetPage, 10);
      if (!isNaN(pageNum)) {
        // Small delay to ensure DOM is rendered
        setTimeout(() => {
          const pageEl = pageRefs.current.get(pageNum);
          if (pageEl) {
            pageEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
            // Add highlight animation
            pageEl.classList.add('highlight-pulse');
            setTimeout(() => pageEl.classList.remove('highlight-pulse'), 2000);
          }
        }, 100);
      }
    }
  }, [notebook, targetPage, loading]);

  // Handle export
  const handleExport = async (format: 'markdown' | 'pdf') => {
    if (!notebook || !authToken) return;

    setExporting(true);
    setExportMenuOpen(false);

    try {
      const response = await fetch(`${API_URL}/notebooks/${notebook.id}/export?format=${format}`, {
        headers: {
          'Authorization': `Bearer ${authToken}`,
        },
      });

      // Check for quota exceeded (402)
      if (response.status === 402) {
        const errorData = await response.json();
        if (errorData.detail?.quota) {
          setQuotaModalData(errorData.detail.quota);
          setQuotaModalOpen(true);
          return;
        }
        throw new Error('Quota exceeded');
      }

      if (!response.ok) {
        // Try to parse JSON error response
        const contentType = response.headers.get('content-type');
        let errorMessage = `Export failed (${response.status})`;

        if (contentType?.includes('application/json')) {
          try {
            const errorData = await response.json();
            errorMessage = errorData.detail || errorMessage;
          } catch {
            // Fallback to text
          }
        } else {
          const errorText = await response.text();
          if (errorText) {
            try {
              const parsed = JSON.parse(errorText);
              errorMessage = parsed.detail || errorText;
            } catch {
              errorMessage = errorText;
            }
          }
        }

        throw new Error(errorMessage);
      }

      // Get filename from Content-Disposition header or generate one
      const contentDisposition = response.headers.get('Content-Disposition');
      let filename = `${notebook.visible_name || 'notebook'}.${format === 'markdown' ? 'md' : 'pdf'}`;
      if (contentDisposition) {
        const match = contentDisposition.match(/filename="([^"]+)"/);
        if (match) {
          filename = match[1];
        }
      }

      // Download the file
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error('Export error:', err);
      setExportError(err instanceof Error ? err.message : 'Export failed');
    } finally {
      setExporting(false);
    }
  };

  // Close export menu when clicking outside
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      const target = e.target as HTMLElement;
      if (!target.closest('[data-export-menu]')) {
        setExportMenuOpen(false);
      }
    };

    if (exportMenuOpen) {
      document.addEventListener('click', handleClickOutside);
    }
    return () => {
      document.removeEventListener('click', handleClickOutside);
    };
  }, [exportMenuOpen]);

  // Handle in-notebook search
  const handleNotebookSearch = useCallback(async (query: string) => {
    // Clear previous timer
    if (searchDebounceTimer.current) clearTimeout(searchDebounceTimer.current);

    if (query.length < 2) {
      setIsNotebookSearchMode(false);
      setNotebookSearchResults(null);
      return;
    }

    // Debounce API call by 300ms
    searchDebounceTimer.current = setTimeout(async () => {
      setNotebookSearchLoading(true);
      setIsNotebookSearchMode(true);

      try {
        const token = isDevelopmentMode
          ? process.env.NEXT_PUBLIC_DEV_AUTH_TOKEN || localStorage.getItem('dev_auth_token') || ''
          : await getToken();

        if (!token || !notebook) return;

        const results = await searchNotebooks(token, query, {
          notebookId: notebook.id,
          limit: 50,
        });
        setNotebookSearchResults(results);
      } catch (err) {
        console.error('Notebook search error:', err);
        setNotebookSearchResults(null);
      } finally {
        setNotebookSearchLoading(false);
      }
    }, 300);
  }, [isDevelopmentMode, getToken, notebook]);

  const clearNotebookSearch = () => {
    setNotebookSearchQuery('');
    setIsNotebookSearchMode(false);
    setNotebookSearchResults(null);
  };

  // Scroll to a specific page
  const scrollToPage = (pageNumber: number) => {
    const pageEl = pageRefs.current.get(pageNumber);
    if (pageEl) {
      pageEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
      pageEl.classList.add('highlight-pulse');
      setTimeout(() => pageEl.classList.remove('highlight-pulse'), 2000);
    }
  };

  if (loading) {
    return (
      <div className="flex h-screen overflow-hidden" style={{ backgroundColor: 'var(--background)' }}>
        <Sidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} />
        {sidebarOpen && (
          <div
            className="fixed inset-0 bg-black/50 z-40 lg:hidden"
            onClick={() => setSidebarOpen(false)}
          />
        )}
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 mx-auto" style={{ borderColor: 'var(--terracotta)' }}></div>
            <p className="mt-4" style={{ color: 'var(--warm-gray)' }}>Loading notebook...</p>
          </div>
        </div>
      </div>
    );
  }

  if (error || !notebook) {
    return (
      <div className="flex h-screen overflow-hidden" style={{ backgroundColor: 'var(--background)' }}>
        <Sidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} />
        {sidebarOpen && (
          <div
            className="fixed inset-0 bg-black/50 z-40 lg:hidden"
            onClick={() => setSidebarOpen(false)}
          />
        )}
        <div className="flex-1 flex items-center justify-center px-4">
          <div className="text-center max-w-md">
            <div style={{ color: 'var(--destructive)', fontSize: '3rem', marginBottom: '1rem' }}>✗</div>
            <h2 style={{ fontSize: '1.5rem', fontWeight: 600, marginBottom: '0.5rem' }}>Error</h2>
            <p style={{ color: 'var(--warm-gray)', marginBottom: '1.5rem' }}>{error || 'Notebook not found'}</p>
            <Link
              href="/dashboard"
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
      </div>
    );
  }

  // Sort pages in reverse order (highest page number first)
  const sortedPages = [...notebook.pages].sort((a, b) => b.page_number - a.page_number);

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

      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Header */}
        <header className="bg-white shadow-sm sticky top-0 z-30" style={{ borderBottom: '1px solid var(--border)' }}>
          <div className="max-w-full mx-auto px-6 lg:px-8 py-4">
            <div className="flex items-center justify-between gap-4">
              {/* Hamburger menu button for mobile */}
              <button
                onClick={() => setSidebarOpen(!sidebarOpen)}
                className="lg:hidden p-2 hover:bg-gray-100 rounded-lg"
              >
                <Menu className="w-5 h-5" />
              </button>

              {/* Breadcrumb navigation */}
              <div className="flex items-center gap-2 flex-1" style={{ fontSize: '0.875em', color: 'var(--warm-gray)' }}>
                <Link href="/dashboard" className="hover:text-[var(--terracotta)] transition-colors">
                  All Notebooks
                </Link>
                <ChevronRight className="w-4 h-4" />
                <span style={{ color: 'var(--warm-charcoal)', fontWeight: 500 }} className="truncate">
                  {notebook.visible_name || notebook.title || 'Untitled'}
                </span>
              </div>

              <div className="flex items-center space-x-4">
                {/* Quota Display */}
                <QuotaDisplay variant="compact" />

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

        {/* Main content */}
        <main className="flex-1 overflow-y-auto px-6 lg:px-8 py-8">
          <div className="max-w-4xl mx-auto">
            {/* Notebook header with metadata and actions */}
            <div className="mb-8">
              <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 mb-4">
                <h1 style={{ fontSize: '2.25rem', fontWeight: 600, color: 'var(--warm-charcoal)', margin: 0 }}>
                  {notebook.visible_name || notebook.title || 'Untitled'}
                </h1>
                {/* In-notebook search */}
                <div className="relative w-full md:w-64">
                  <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4" style={{ color: 'var(--warm-gray)' }} />
                  <input
                    type="text"
                    placeholder="Search in this notebook..."
                    value={notebookSearchQuery}
                    onChange={(e) => {
                      setNotebookSearchQuery(e.target.value);
                      handleNotebookSearch(e.target.value);
                    }}
                    className="w-full pl-9 pr-8 py-2 rounded-lg"
                    style={{
                      border: '1px solid var(--border)',
                      fontSize: '0.875em',
                      backgroundColor: 'var(--card)',
                      color: 'var(--foreground)'
                    }}
                  />
                  {notebookSearchLoading && (
                    <Loader2
                      className="absolute right-8 top-1/2 transform -translate-y-1/2 w-4 h-4 animate-spin"
                      style={{ color: 'var(--terracotta)' }}
                    />
                  )}
                  {notebookSearchQuery && (
                    <button
                      onClick={clearNotebookSearch}
                      className="absolute right-2 top-1/2 transform -translate-y-1/2"
                      style={{ color: 'var(--warm-gray)' }}
                    >
                      <X className="w-4 h-4" />
                    </button>
                  )}
                </div>
              </div>

              {/* Metadata row */}
              <div className="flex flex-wrap items-center gap-6 mb-4" style={{ fontSize: '0.875em', color: 'var(--warm-gray)' }}>
                <div className="flex items-center gap-2">
                  <Calendar className="w-4 h-4" />
                  <span>
                    Created {notebook.created_at ? new Date(notebook.created_at).toLocaleDateString('en-US', {
                      year: 'numeric', month: 'short', day: 'numeric'
                    }) : 'Unknown'}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <Clock className="w-4 h-4" />
                  <span>
                    Last synced {notebook.last_synced_at ? new Date(notebook.last_synced_at).toLocaleDateString('en-US', {
                      year: 'numeric', month: 'short', day: 'numeric'
                    }) : 'Never'}
                  </span>
                </div>
                <span>
                  <strong>{notebook.pages.length}</strong> {notebook.pages.length === 1 ? 'page' : 'pages'}
                </span>
                <span>
                  <strong style={{ textTransform: 'capitalize' }}>{notebook.document_type}</strong>
                </span>
              </div>

              {/* Action buttons */}
              <div className="flex gap-3">
                <div className="relative" data-export-menu>
                  <button
                    onClick={() => setExportMenuOpen(!exportMenuOpen)}
                    disabled={exporting}
                    className="px-4 py-2 rounded-lg transition-all flex items-center gap-2"
                    style={{
                      backgroundColor: 'var(--terracotta)',
                      color: 'white',
                      fontSize: '0.875em',
                      fontWeight: 500,
                      border: 'none',
                      cursor: exporting ? 'not-allowed' : 'pointer',
                      opacity: exporting ? 0.7 : 1,
                    }}
                    onMouseEnter={(e) => {
                      if (!exporting) e.currentTarget.style.opacity = '0.9';
                    }}
                    onMouseLeave={(e) => {
                      if (!exporting) e.currentTarget.style.opacity = '1';
                    }}
                  >
                    {exporting ? (
                      <>
                        <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                        Exporting...
                      </>
                    ) : (
                      <>
                        <Download className="w-4 h-4" />
                        Export
                        <ChevronDown className="w-4 h-4" />
                      </>
                    )}
                  </button>

                  {/* Dropdown menu */}
                  {exportMenuOpen && !exporting && (
                    <div
                      className="absolute top-full left-0 mt-2 w-56 rounded-lg shadow-lg z-50"
                      style={{
                        backgroundColor: 'var(--card)',
                        border: '1px solid var(--border)',
                      }}
                    >
                      <button
                        onClick={() => handleExport('markdown')}
                        className="w-full px-4 py-3 flex items-start gap-3 text-left hover:bg-[var(--soft-cream)] transition-colors rounded-t-lg"
                      >
                        <FileText className="w-5 h-5 mt-0.5" style={{ color: 'var(--terracotta)' }} />
                        <div>
                          <div style={{ fontWeight: 500, color: 'var(--warm-charcoal)' }}>Markdown</div>
                          <div style={{ fontSize: '0.75em', color: 'var(--warm-gray)' }}>OCR text as .md file</div>
                        </div>
                      </button>
                      <button
                        onClick={() => handleExport('pdf')}
                        className="w-full px-4 py-3 flex items-start gap-3 text-left hover:bg-[var(--soft-cream)] transition-colors rounded-b-lg"
                        style={{ borderTop: '1px solid var(--border)' }}
                      >
                        <FileDown className="w-5 h-5 mt-0.5" style={{ color: 'var(--terracotta)' }} />
                        <div>
                          <div style={{ fontWeight: 500, color: 'var(--warm-charcoal)' }}>PDF</div>
                          <div style={{ fontSize: '0.75em', color: 'var(--warm-gray)' }}>Combined page PDFs</div>
                        </div>
                      </button>
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Sync Progress */}
            <SyncProgress pages={notebook.pages} />

            {/* In-notebook search results */}
            {isNotebookSearchMode && notebookSearchResults ? (
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <p style={{ fontSize: '0.925em', color: 'var(--warm-gray)' }}>
                    {notebookSearchResults.total_results > 0 ? (
                      <>{notebookSearchResults.results[0]?.matched_pages.length || 0} matches in this notebook</>
                    ) : (
                      <>No matches found for "{notebookSearchQuery}"</>
                    )}
                  </p>
                  <button
                    onClick={clearNotebookSearch}
                    style={{ fontSize: '0.875em', color: 'var(--terracotta)' }}
                  >
                    Show all pages
                  </button>
                </div>
                {notebookSearchResults.results[0]?.matched_pages.map((matchedPage) => (
                  <button
                    key={matchedPage.page_id}
                    onClick={() => {
                      clearNotebookSearch();
                      setTimeout(() => scrollToPage(matchedPage.page_number), 100);
                    }}
                    className="block w-full text-left p-4 rounded-lg transition-all hover:border-[var(--terracotta)]"
                    style={{
                      backgroundColor: 'var(--card)',
                      border: '1px solid var(--border)',
                    }}
                  >
                    <div style={{ fontWeight: 500, color: 'var(--warm-charcoal)', marginBottom: '0.5rem' }}>
                      Page {matchedPage.page_number}
                    </div>
                    <div style={{ fontSize: '0.875em', color: 'var(--warm-gray)' }}>
                      {matchedPage.snippet.text}
                    </div>
                  </button>
                ))}
              </div>
            ) : sortedPages.length === 0 ? (
              <div className="text-center py-12 rounded-lg" style={{ backgroundColor: 'var(--card)', border: '1px solid var(--border)' }}>
                <h3 style={{ fontSize: '1.25rem', fontWeight: 600, marginBottom: '0.5rem' }}>
                  No pages found
                </h3>
                <p style={{ color: 'var(--warm-gray)' }}>
                  This notebook doesn't have any pages yet.
                </p>
              </div>
            ) : (
              /* Pages */
              <div className="space-y-6">
                {sortedPages.map((page) => (
                  <PageCard
                    key={page.id}
                    page={page}
                    token={authToken}
                    copiedPageId={copiedPageId}
                    setCopiedPageId={setCopiedPageId}
                    quota={quota}
                    isTargetPage={targetPage === String(page.page_number)}
                    cardRef={(el) => el && pageRefs.current.set(page.page_number, el)}
                  />
                ))}
              </div>
            )}
          </div>
        </main>
      </div>

      {/* Quota Exceeded Modal */}
      <QuotaExceededModal
        isOpen={quotaModalOpen}
        onClose={() => setQuotaModalOpen(false)}
        quota={quotaModalData}
      />

      {/* Export Error Modal */}
      {exportError && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4"
          style={{ backgroundColor: 'rgba(0, 0, 0, 0.5)' }}
          onClick={() => setExportError(null)}
        >
          <div
            className="relative max-w-md w-full rounded-lg shadow-2xl p-6"
            style={{ backgroundColor: 'var(--card)' }}
            onClick={(e) => e.stopPropagation()}
          >
            {/* Icon */}
            <div
              className="w-12 h-12 rounded-full flex items-center justify-center mx-auto mb-4"
              style={{ backgroundColor: 'rgba(220, 38, 38, 0.1)' }}
            >
              <svg className="w-6 h-6" style={{ color: 'var(--destructive)' }} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
            </div>

            {/* Title */}
            <h3 style={{
              fontSize: '1.25rem',
              fontWeight: 600,
              color: 'var(--warm-charcoal)',
              textAlign: 'center',
              marginBottom: '0.5rem'
            }}>
              Export Failed
            </h3>

            {/* Message */}
            <p style={{
              fontSize: '0.925em',
              color: 'var(--warm-gray)',
              textAlign: 'center',
              marginBottom: '1.5rem'
            }}>
              {exportError}
            </p>

            {/* Button */}
            <button
              onClick={() => setExportError(null)}
              className="w-full px-4 py-2 rounded-lg transition-colors font-medium"
              style={{
                backgroundColor: 'var(--terracotta)',
                color: 'white',
              }}
            >
              Close
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// Loading fallback for Suspense
function NotebookLoading() {
  return (
    <div className="flex h-screen items-center justify-center" style={{ backgroundColor: 'var(--background)' }}>
      <div className="text-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 mx-auto" style={{ borderColor: 'var(--terracotta)' }}></div>
        <p className="mt-4" style={{ color: 'var(--warm-gray)' }}>Loading notebook...</p>
      </div>
    </div>
  );
}

// Wrap in Suspense for useSearchParams
export default function NotebookPage() {
  return (
    <Suspense fallback={<NotebookLoading />}>
      <NotebookPageContent />
    </Suspense>
  );
}
