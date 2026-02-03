'use client';

import Link from 'next/link';
import { BookOpen, FileText, ChevronRight, Search } from 'lucide-react';
import type { SearchResult, SearchSnippet, MatchedPage } from '@/lib/api';

interface SearchResultsProps {
  results: SearchResult[];
  query: string;
  totalResults: number;
  hasMore: boolean;
  onLoadMore?: () => void;
  loadingMore?: boolean;
}

function HighlightedText({ snippet }: { snippet: SearchSnippet }) {
  const { text, highlights } = snippet;
  if (!highlights || highlights.length === 0) return <span>{text}</span>;

  const parts: JSX.Element[] = [];
  let lastIndex = 0;

  // Sort highlights by start position to handle them in order
  const sortedHighlights = [...highlights].sort((a, b) => a[0] - b[0]);

  sortedHighlights.forEach(([start, end], i) => {
    // Add text before highlight
    if (start > lastIndex) {
      parts.push(<span key={`t-${i}`}>{text.slice(lastIndex, start)}</span>);
    }
    // Add highlighted text
    parts.push(
      <mark
        key={`h-${i}`}
        style={{
          backgroundColor: 'rgba(200, 90, 84, 0.2)',
          color: 'var(--terracotta)',
          padding: '0 2px',
          borderRadius: '2px'
        }}
      >
        {text.slice(start, end)}
      </mark>
    );
    lastIndex = end;
  });

  // Add remaining text after last highlight
  if (lastIndex < text.length) {
    parts.push(<span key="end">{text.slice(lastIndex)}</span>);
  }

  return <>{parts}</>;
}

function MatchedPageItem({ page, notebookId }: { page: MatchedPage; notebookId: number }) {
  return (
    <Link
      href={`/notebooks/${notebookId}?page=${page.page_number}`}
      className="flex items-start gap-3 p-3 rounded-lg transition-all hover:bg-[var(--soft-cream)] group"
      style={{ borderLeft: '2px solid var(--border)' }}
      onMouseEnter={(e) => {
        e.currentTarget.style.borderLeftColor = 'var(--terracotta)';
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.borderLeftColor = 'var(--border)';
      }}
    >
      <FileText
        className="w-4 h-4 flex-shrink-0 mt-0.5"
        style={{ color: 'var(--warm-gray)' }}
      />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-1">
          <span
            style={{
              fontSize: '0.75em',
              fontWeight: 500,
              color: 'var(--warm-gray)'
            }}
          >
            Page {page.page_number}
          </span>
        </div>
        <p
          style={{
            fontSize: '0.875em',
            color: 'var(--warm-charcoal)',
            lineHeight: 1.5,
            margin: 0
          }}
        >
          <HighlightedText snippet={page.snippet} />
        </p>
      </div>
      <ChevronRight
        className="w-4 h-4 flex-shrink-0 opacity-0 group-hover:opacity-100 transition-opacity"
        style={{ color: 'var(--warm-gray)' }}
      />
    </Link>
  );
}

function SearchResultCard({ result }: { result: SearchResult }) {
  const hasMatchedPages = result.matched_pages && result.matched_pages.length > 0;

  return (
    <div
      className="rounded-lg overflow-hidden"
      style={{
        backgroundColor: 'var(--card)',
        border: '1px solid var(--border)',
        boxShadow: 'var(--shadow-sm)'
      }}
    >
      {/* Notebook header */}
      <Link
        href={`/notebooks/${result.notebook_id}`}
        className="flex items-center gap-3 p-4 transition-all hover:bg-[var(--soft-cream)] group"
        style={{ borderBottom: hasMatchedPages ? '1px solid var(--border)' : 'none' }}
      >
        <BookOpen
          className="w-5 h-5 flex-shrink-0"
          style={{ color: 'var(--terracotta)' }}
        />
        <div className="flex-1 min-w-0">
          <h3
            className="group-hover:text-[var(--terracotta)] transition-colors"
            style={{
              fontSize: '1em',
              fontWeight: 600,
              color: 'var(--warm-charcoal)',
              margin: 0,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap'
            }}
          >
            {result.visible_name}
          </h3>
          {result.full_path && (
            <p
              style={{
                fontSize: '0.75em',
                color: 'var(--warm-gray)',
                margin: '0.25rem 0 0 0'
              }}
            >
              {result.full_path}
            </p>
          )}
        </div>
        <div className="flex items-center gap-2">
          {result.name_match && (
            <span
              style={{
                fontSize: '0.7em',
                fontWeight: 500,
                color: 'var(--terracotta)',
                backgroundColor: 'rgba(200, 90, 84, 0.1)',
                padding: '2px 6px',
                borderRadius: '4px'
              }}
            >
              Name match
            </span>
          )}
          {result.total_matched_pages > 0 && (
            <span
              style={{
                fontSize: '0.75em',
                color: 'var(--warm-gray)'
              }}
            >
              {result.total_matched_pages} page{result.total_matched_pages !== 1 ? 's' : ''}
            </span>
          )}
          <ChevronRight
            className="w-5 h-5"
            style={{ color: 'var(--warm-gray)' }}
          />
        </div>
      </Link>

      {/* Matched pages */}
      {hasMatchedPages && (
        <div className="p-2 space-y-1">
          {result.matched_pages.map((page) => (
            <MatchedPageItem
              key={page.page_id}
              page={page}
              notebookId={result.notebook_id}
            />
          ))}
        </div>
      )}
    </div>
  );
}

export function SearchResults({
  results,
  query,
  totalResults,
  hasMore,
  onLoadMore,
  loadingMore
}: SearchResultsProps) {
  if (results.length === 0) {
    return (
      <div
        className="text-center py-12 rounded-lg"
        style={{
          backgroundColor: 'var(--card)',
          border: '1px solid var(--border)'
        }}
      >
        <Search
          className="w-16 h-16 mx-auto mb-4"
          style={{ color: 'var(--warm-gray)', opacity: 0.5 }}
        />
        <h3
          style={{
            fontSize: '1.25rem',
            fontWeight: 600,
            marginBottom: '0.5rem',
            color: 'var(--warm-charcoal)'
          }}
        >
          No results found
        </h3>
        <p style={{ color: 'var(--warm-gray)' }}>
          No notebooks or pages match &quot;{query}&quot;
        </p>
      </div>
    );
  }

  return (
    <div>
      {/* Results header */}
      <div className="mb-4">
        <p style={{ fontSize: '0.875em', color: 'var(--warm-gray)' }}>
          {totalResults} result{totalResults !== 1 ? 's' : ''} for &quot;{query}&quot;
        </p>
      </div>

      {/* Results list */}
      <div className="space-y-4">
        {results.map((result) => (
          <SearchResultCard key={result.notebook_id} result={result} />
        ))}
      </div>

      {/* Load more button */}
      {hasMore && onLoadMore && (
        <div className="mt-6 text-center">
          <button
            onClick={onLoadMore}
            disabled={loadingMore}
            className="px-6 py-2 rounded-lg transition-colors"
            style={{
              backgroundColor: 'var(--soft-cream)',
              color: 'var(--warm-charcoal)',
              border: '1px solid var(--border)',
              fontSize: '0.875em',
              fontWeight: 500,
              cursor: loadingMore ? 'not-allowed' : 'pointer',
              opacity: loadingMore ? 0.6 : 1
            }}
          >
            {loadingMore ? 'Loading...' : 'Load more results'}
          </button>
        </div>
      )}
    </div>
  );
}
