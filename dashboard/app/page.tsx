'use client';

import { useAuth, UserButton } from '@clerk/nextjs';
import { useEffect, useState } from 'react';
import Link from 'next/link';
import { getNotebooksTree, type NotebookTree } from '@/lib/api';
import NotebookTree from '@/components/NotebookTree';

export default function Home() {
  const { getToken, isSignedIn } = useAuth();
  const [notebookTree, setNotebookTree] = useState<NotebookTree | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchNotebooks = async () => {
    if (!isSignedIn) {
      setLoading(false);
      return;
    }

    try {
      setError(null);
      const token = await getToken();
      if (!token) {
        throw new Error('Failed to get authentication token');
      }

      const data = await getNotebooksTree(token);
      setNotebookTree(data);
    } catch (err) {
      console.error('Error fetching notebooks:', err);
      setError(err instanceof Error ? err.message : 'Failed to fetch notebooks');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchNotebooks();
  }, [isSignedIn, getToken]);

  // Header component that's always visible
  const Header = () => (
    <header className="bg-white shadow-sm sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <h1 className="text-2xl font-bold text-gray-900">📓 rMirror</h1>
          </div>
          <div className="flex items-center space-x-4">
            {isSignedIn && <UserButton afterSignOutUrl="/" />}
          </div>
        </div>
      </div>
    </header>
  );

  if (loading) {
    return (
      <>
        <Header />
        <div className="min-h-screen flex items-center justify-center bg-gray-50">
          <div className="text-center">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-purple-600 mx-auto"></div>
            <p className="mt-4 text-gray-600">Loading notebooks...</p>
          </div>
        </div>
      </>
    );
  }

  if (error) {
    return (
      <>
        <Header />
        <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
          <div className="text-center max-w-md">
            <div className="text-red-600 text-5xl mb-4">✗</div>
            <h2 className="text-2xl font-bold text-gray-900 mb-2">Error</h2>
            <p className="text-gray-600 mb-6">{error}</p>
            <div className="flex flex-col sm:flex-row gap-3 justify-center">
              <button
                onClick={() => fetchNotebooks()}
                className="px-6 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition-colors"
              >
                Try Again
              </button>
              <Link
                href="/"
                className="px-6 py-2 bg-gray-200 text-gray-700 rounded-lg hover:bg-gray-300 transition-colors"
              >
                Go Home
              </Link>
            </div>
          </div>
        </div>
      </>
    );
  }

  return (
    <>
      <Header />
      <div className="min-h-screen bg-gray-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
          <div className="flex items-center justify-between mb-8">
            <div>
              <h1 className="text-3xl font-bold text-gray-900 mb-2">
                Your Notebooks
              </h1>
              {notebookTree && (
                <p className="text-gray-600">
                  {notebookTree.total} {notebookTree.total === 1 ? 'item' : 'items'}
                </p>
              )}
            </div>
          </div>

          {!notebookTree || notebookTree.total === 0 ? (
            <div className="text-center py-12 bg-white rounded-lg border border-gray-200">
              <div className="text-gray-400 text-6xl mb-4">📚</div>
              <h3 className="text-xl font-semibold text-gray-900 mb-2">
                No notebooks yet
              </h3>
              <p className="text-gray-600">
                Sync your reMarkable notebooks using the Mac agent to get started.
              </p>
            </div>
          ) : (
            <NotebookTree nodes={notebookTree.tree} />
          )}
        </div>
      </div>
    </>
  );
}
