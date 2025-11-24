'use client';

import { useAuth } from '@clerk/nextjs';
import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import { getNotebook, type NotebookWithPages } from '@/lib/api';

export default function NotebookPage() {
  const params = useParams();
  const router = useRouter();
  const { getToken, isSignedIn } = useAuth();
  const [notebook, setNotebook] = useState<NotebookWithPages | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isSignedIn) {
      router.push('/');
      return;
    }

    const fetchNotebook = async () => {
      try {
        const token = await getToken();
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
  }, [params.id, isSignedIn, getToken, router]);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-purple-600 mx-auto"></div>
          <p className="mt-4 text-gray-600">Loading notebook...</p>
        </div>
      </div>
    );
  }

  if (error || !notebook) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="text-center">
          <div className="text-red-600 text-5xl mb-4">✗</div>
          <h2 className="text-2xl font-bold text-gray-900 mb-2">Error</h2>
          <p className="text-gray-600 mb-6">{error || 'Notebook not found'}</p>
          <Link
            href="/"
            className="inline-block bg-purple-600 text-white px-6 py-2 rounded-lg hover:bg-purple-700 transition-colors"
          >
            ← Back to notebooks
          </Link>
        </div>
      </div>
    );
  }

  const sortedPages = [...notebook.pages].sort((a, b) => a.page_number - b.page_number);

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        {/* Header */}
        <div className="mb-8">
          <Link
            href="/"
            className="inline-flex items-center text-purple-600 hover:text-purple-700 mb-4"
          >
            ← Back to notebooks
          </Link>

          <h1 className="text-3xl font-bold text-gray-900 mb-2">
            {notebook.visible_name || notebook.title || 'Untitled'}
          </h1>

          <div className="flex items-center gap-4 text-sm text-gray-600">
            {notebook.author && (
              <span>
                <span className="font-medium">Author:</span> {notebook.author}
              </span>
            )}
            <span>
              <span className="font-medium">Type:</span> {notebook.document_type.toUpperCase()}
            </span>
            <span>
              <span className="font-medium">Pages:</span> {notebook.pages.length}
            </span>
          </div>
        </div>

        {/* Pages */}
        {sortedPages.length === 0 ? (
          <div className="text-center py-12 bg-white rounded-lg shadow">
            <div className="text-gray-400 text-6xl mb-4">📄</div>
            <h3 className="text-xl font-semibold text-gray-900 mb-2">
              No pages found
            </h3>
            <p className="text-gray-600">
              This notebook doesn't have any pages yet.
            </p>
          </div>
        ) : (
          <div className="space-y-6">
            {sortedPages.map((page) => (
              <div
                key={page.id}
                className="bg-white rounded-lg shadow-md p-6"
              >
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-lg font-semibold text-gray-900">
                    Page {page.page_number}
                  </h3>

                  <span
                    className={`px-3 py-1 rounded-full text-sm font-medium ${
                      page.ocr_status === 'completed'
                        ? 'bg-green-100 text-green-800'
                        : page.ocr_status === 'processing'
                        ? 'bg-blue-100 text-blue-800'
                        : page.ocr_status === 'failed'
                        ? 'bg-red-100 text-red-800'
                        : 'bg-gray-100 text-gray-800'
                    }`}
                  >
                    {page.ocr_status}
                  </span>
                </div>

                {page.ocr_status === 'completed' && page.ocr_text ? (
                  <div className="prose max-w-none">
                    <pre className="whitespace-pre-wrap text-gray-700 font-sans bg-gray-50 p-4 rounded border border-gray-200">
                      {page.ocr_text}
                    </pre>
                  </div>
                ) : page.ocr_status === 'failed' && page.ocr_error ? (
                  <div className="bg-red-50 border border-red-200 rounded p-4">
                    <p className="text-red-800 font-medium mb-2">OCR Failed</p>
                    <p className="text-red-600 text-sm">{page.ocr_error}</p>
                  </div>
                ) : page.ocr_status === 'processing' ? (
                  <div className="bg-blue-50 border border-blue-200 rounded p-4 flex items-center">
                    <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-blue-600 mr-3"></div>
                    <p className="text-blue-800">Processing OCR...</p>
                  </div>
                ) : (
                  <div className="bg-gray-50 border border-gray-200 rounded p-4">
                    <p className="text-gray-600">OCR pending</p>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
