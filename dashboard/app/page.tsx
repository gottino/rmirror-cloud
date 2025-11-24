'use client';

import { useAuth } from '@clerk/nextjs';
import { useEffect, useState } from 'react';
import Link from 'next/link';
import { getNotebooks, type Notebook } from '@/lib/api';

export default function Home() {
  const { getToken, isSignedIn } = useAuth();
  const [notebooks, setNotebooks] = useState<Notebook[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isSignedIn) {
      setLoading(false);
      return;
    }

    const fetchNotebooks = async () => {
      try {
        const token = await getToken();
        if (!token) {
          throw new Error('Failed to get authentication token');
        }

        const data = await getNotebooks(token);
        setNotebooks(data);
      } catch (err) {
        console.error('Error fetching notebooks:', err);
        setError(err instanceof Error ? err.message : 'Failed to fetch notebooks');
      } finally {
        setLoading(false);
      }
    };

    fetchNotebooks();
  }, [isSignedIn, getToken]);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-purple-600 mx-auto"></div>
          <p className="mt-4 text-gray-600">Loading notebooks...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="text-center">
          <div className="text-red-600 text-5xl mb-4">✗</div>
          <h2 className="text-2xl font-bold text-gray-900 mb-2">Error</h2>
          <p className="text-gray-600">{error}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <div className="text-center mb-12">
          <h1 className="text-4xl font-bold text-gray-900 mb-4">
            📓 rMirror Notebooks
          </h1>
          <p className="text-lg text-gray-600">
            View your transcribed handwritten notebooks
          </p>
        </div>

        {notebooks.length === 0 ? (
          <div className="text-center py-12">
            <div className="text-gray-400 text-6xl mb-4">📚</div>
            <h3 className="text-xl font-semibold text-gray-900 mb-2">
              No notebooks yet
            </h3>
            <p className="text-gray-600">
              Sync your reMarkable notebooks using the Mac agent to get started.
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {notebooks.map((notebook) => (
              <Link
                key={notebook.id}
                href={`/notebooks/${notebook.id}`}
                className="block bg-white rounded-lg shadow-md hover:shadow-lg transition-shadow duration-200 p-6"
              >
                <div className="flex items-start justify-between mb-4">
                  <h3 className="text-lg font-semibold text-gray-900 line-clamp-2">
                    {notebook.visible_name || notebook.title || 'Untitled'}
                  </h3>
                  <span className="ml-2 text-2xl">📓</span>
                </div>

                <div className="space-y-2 text-sm text-gray-600">
                  {notebook.author && (
                    <p className="flex items-center">
                      <span className="font-medium mr-2">Author:</span>
                      {notebook.author}
                    </p>
                  )}

                  <p className="flex items-center">
                    <span className="font-medium mr-2">Type:</span>
                    {notebook.document_type.toUpperCase()}
                  </p>

                  <p className="flex items-center">
                    <span className="font-medium mr-2">Last synced:</span>
                    {notebook.last_synced_at
                      ? new Date(notebook.last_synced_at).toLocaleDateString()
                      : 'Never'}
                  </p>
                </div>

                <div className="mt-4 pt-4 border-t border-gray-200">
                  <span className="text-purple-600 font-medium text-sm hover:text-purple-700">
                    View notebook →
                  </span>
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
