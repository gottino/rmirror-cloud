'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import type { NotebookTreeNode } from '@/lib/api';

interface NotebookCardProps {
  notebook: NotebookTreeNode;
  variant?: 'grid' | 'list';
}

export function NotebookCard({ notebook, variant = 'grid' }: NotebookCardProps) {
  const router = useRouter();

  const formatDate = (dateString: string | null) => {
    if (!dateString) return null;
    return new Date(dateString).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
    });
  };

  const renderPreviewContent = () => {
    if (notebook.preview) {
      return (
        <p
          style={{
            fontSize: variant === 'grid' ? '0.75rem' : '0.625rem',
            color: 'var(--warm-ink)',
            lineHeight: 1.5,
            margin: 0,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            display: '-webkit-box',
            WebkitLineClamp: variant === 'grid' ? 7 : 4,
            WebkitBoxOrient: 'vertical',
            fontFamily: 'var(--font-body)',
          }}
        >
          {notebook.preview}
        </p>
      );
    }

    if (notebook.sync_progress && notebook.sync_progress.not_synced_pages > 0) {
      return (
        <div className="flex flex-col items-center justify-center w-full h-full">
          <svg
            className="w-6 h-6 mb-2"
            style={{ color: 'var(--muted-sepia)' }}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={1.5}
              d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
            />
          </svg>
          <span
            style={{
              fontSize: '0.75rem',
              color: 'var(--muted-sepia)',
              textAlign: 'center',
              fontWeight: 500,
              fontFamily: 'var(--font-body)',
            }}
          >
            Awaiting upload
          </span>
          <span
            style={{
              fontSize: '0.625rem',
              color: 'var(--muted-sepia)',
              textAlign: 'center',
              fontFamily: 'var(--font-body)',
              marginTop: '0.25rem',
            }}
          >
            {notebook.sync_progress.synced_pages}/{notebook.sync_progress.total_pages} ready
          </span>
        </div>
      );
    }

    if (notebook.sync_progress && notebook.sync_progress.pending_quota_pages > 0) {
      return (
        <div className="flex flex-col items-center justify-center w-full h-full">
          <span
            style={{
              fontSize: '0.75rem',
              color: 'var(--amber-gold)',
              textAlign: 'center',
              fontWeight: 500,
              fontFamily: 'var(--font-body)',
            }}
          >
            OCR Pending
          </span>
          <button
            onClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
              router.push('/billing');
            }}
            style={{
              fontSize: '0.625rem',
              color: 'var(--primary)',
              textAlign: 'center',
              textDecoration: 'underline',
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              padding: 0,
              marginTop: '0.25rem',
              fontFamily: 'var(--font-body)',
            }}
          >
            Upgrade
          </button>
        </div>
      );
    }

    return (
      <div className="flex flex-col items-center justify-center w-full h-full">
        <span
          style={{
            fontSize: '0.75rem',
            color: 'var(--amber-gold)',
            textAlign: 'center',
            fontWeight: 500,
            fontFamily: 'var(--font-body)',
          }}
        >
          OCR Pending
        </span>
        <button
          onClick={(e) => {
            e.preventDefault();
            e.stopPropagation();
            router.push('/billing');
          }}
          style={{
            fontSize: '0.625rem',
            color: 'var(--primary)',
            textAlign: 'center',
            textDecoration: 'underline',
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            padding: 0,
            marginTop: '0.25rem',
            fontFamily: 'var(--font-body)',
          }}
        >
          Upgrade
        </button>
      </div>
    );
  };

  if (variant === 'list') {
    return (
      <Link
        href={`/notebooks/${notebook.id}`}
        className="flex items-center gap-4 p-4 transition-all group"
        style={{
          backgroundColor: 'var(--card-paper)',
          border: '1px solid var(--border-sketch)',
          borderRadius: 'var(--radius-sm)',
          boxShadow: 'var(--shadow-sm)',
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.boxShadow = 'var(--shadow-md)';
          e.currentTarget.style.borderColor = 'var(--primary)';
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.boxShadow = 'var(--shadow-sm)';
          e.currentTarget.style.borderColor = 'var(--border-sketch)';
        }}
      >
        {/* Preview thumbnail */}
        <div
          className="w-12 h-16 flex-shrink-0 flex items-start p-2 overflow-hidden"
          style={{
            backgroundColor: 'var(--card-paper)',
            border: '1px solid var(--border-sketch)',
            borderRadius: 'var(--radius-sm)',
          }}
        >
          {renderPreviewContent()}
        </div>

        {/* Meta */}
        <div className="flex-1 min-w-0">
          <h4
            className="group-hover:text-[var(--primary)] transition-colors"
            style={{
              fontSize: '0.9375rem',
              fontWeight: 600,
              color: 'var(--warm-ink)',
              marginBottom: '0.125rem',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
              fontFamily: 'var(--font-display)',
            }}
          >
            {notebook.visible_name}
          </h4>
          <p
            style={{
              fontSize: '0.8125rem',
              color: 'var(--muted-sepia)',
              fontFamily: 'var(--font-body)',
            }}
          >
            {formatDate(notebook.last_synced_at) || 'Never synced'}
          </p>
        </div>
      </Link>
    );
  }

  // Grid variant (default)
  return (
    <Link
      href={`/notebooks/${notebook.id}`}
      className="flex flex-col transition-all group"
      style={{
        backgroundColor: 'var(--card-paper)',
        border: '1px solid var(--border-sketch)',
        borderRadius: 'var(--radius-sm)',
        boxShadow: 'var(--shadow-md)',
        overflow: 'hidden',
        width: 280,
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.boxShadow = 'var(--shadow-lg)';
        e.currentTarget.style.transform = 'translateY(-2px)';
        e.currentTarget.style.borderColor = 'var(--primary)';
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.boxShadow = 'var(--shadow-md)';
        e.currentTarget.style.transform = 'translateY(0)';
        e.currentTarget.style.borderColor = 'var(--border-sketch)';
      }}
    >
      {/* Preview area */}
      <div
        className="flex items-start p-4 overflow-hidden"
        style={{
          height: 160,
          borderBottom: '1px solid var(--border-sketch)',
        }}
      >
        {renderPreviewContent()}
      </div>

      {/* Meta area */}
      <div className="p-4" style={{ gap: '0.25rem' }}>
        <h4
          className="group-hover:text-[var(--primary)] transition-colors"
          style={{
            fontSize: '0.9375rem',
            fontWeight: 600,
            color: 'var(--warm-ink)',
            marginBottom: '0.25rem',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
            fontFamily: 'var(--font-display)',
          }}
        >
          {notebook.visible_name}
        </h4>
        <p
          style={{
            fontSize: '0.8125rem',
            color: 'var(--muted-sepia)',
            fontFamily: 'var(--font-body)',
          }}
        >
          {formatDate(notebook.last_synced_at) || 'Never synced'}
        </p>
      </div>
    </Link>
  );
}
