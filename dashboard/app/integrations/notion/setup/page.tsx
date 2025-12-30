'use client';

import { Suspense, useEffect, useState } from 'react';
import { useAuth, UserButton } from '@clerk/nextjs';
import { useRouter, useSearchParams } from 'next/navigation';
import { Menu } from 'lucide-react';
import Sidebar from '@/components/Sidebar';
import {
  listNotionDatabases,
  listNotionPages,
  createNotionDatabase,
  selectNotionDatabase,
  NotionDatabase,
  NotionPage,
} from '@/lib/api';

function NotionSetupContent() {
  const { getToken } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const databaseType = (searchParams.get('type') as 'notebooks' | 'todos') || 'notebooks';
  const [sidebarOpen, setSidebarOpen] = useState(false);

  // Development mode bypass
  const isDevelopmentMode = process.env.NEXT_PUBLIC_DEV_MODE === 'true';

  const [step, setStep] = useState<'choose' | 'select' | 'create'>('choose');
  const [databases, setDatabases] = useState<NotionDatabase[]>([]);
  const [pages, setPages] = useState<NotionPage[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Create new database state
  const [newDbTitle, setNewDbTitle] = useState(
    databaseType === 'todos' ? 'rMirror Tasks' : 'rMirror Notebooks'
  );
  const [selectedParentPage, setSelectedParentPage] = useState<string>('');

  useEffect(() => {
    if (step === 'select') {
      loadDatabases();
    } else if (step === 'create') {
      loadPages();
    }
  }, [step]);

  async function loadDatabases() {
    setLoading(true);
    try {
      const token = isDevelopmentMode
        ? process.env.NEXT_PUBLIC_DEV_AUTH_TOKEN || localStorage.getItem('dev_auth_token') || ''
        : await getToken();
      if (!token) return;

      const data = await listNotionDatabases(token);
      setDatabases(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load databases');
    } finally {
      setLoading(false);
    }
  }

  async function loadPages() {
    setLoading(true);
    try {
      const token = isDevelopmentMode
        ? process.env.NEXT_PUBLIC_DEV_AUTH_TOKEN || localStorage.getItem('dev_auth_token') || ''
        : await getToken();
      if (!token) return;

      const data = await listNotionPages(token);
      setPages(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load pages');
    } finally {
      setLoading(false);
    }
  }

  async function handleSelectDatabase(databaseId: string) {
    setLoading(true);
    try {
      const token = isDevelopmentMode
        ? process.env.NEXT_PUBLIC_DEV_AUTH_TOKEN || localStorage.getItem('dev_auth_token') || ''
        : await getToken();
      if (!token) return;

      await selectNotionDatabase(token, databaseId, databaseType);
      router.push('/integrations?success=true');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to select database');
    } finally {
      setLoading(false);
    }
  }

  async function handleCreateDatabase() {
    if (!newDbTitle.trim()) {
      setError('Please enter a database title');
      return;
    }

    setLoading(true);
    try {
      const token = isDevelopmentMode
        ? process.env.NEXT_PUBLIC_DEV_AUTH_TOKEN || localStorage.getItem('dev_auth_token') || ''
        : await getToken();
      if (!token) return;

      await createNotionDatabase(
        token,
        newDbTitle,
        databaseType,
        selectedParentPage || undefined
      );
      router.push('/integrations?success=true');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create database');
    } finally {
      setLoading(false);
    }
  }

  const title = databaseType === 'todos' ? 'Notion Todos' : 'Notion Notebooks';
  const description =
    databaseType === 'todos'
      ? 'Set up a Notion database to sync your extracted todos'
      : 'Set up a Notion database to sync your notebooks';

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

      <main className="flex-1 overflow-auto">
        {/* Header */}
        <header className="sticky top-0 z-30 border-b bg-white px-6 py-4" style={{ borderColor: 'var(--border)' }}>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <button
                onClick={() => setSidebarOpen(!sidebarOpen)}
                className="lg:hidden p-2 hover:bg-gray-100 rounded-lg"
              >
                <Menu className="w-5 h-5" />
              </button>
              <div>
                <h1 className="text-2xl font-semibold" style={{ color: 'var(--warm-charcoal)' }}>
                  {title} Setup
                </h1>
                <p className="text-sm" style={{ color: 'var(--warm-gray)' }}>
                  {description}
                </p>
              </div>
            </div>
            <UserButton />
          </div>
        </header>

        {/* Content */}
        <div className="p-6" style={{ backgroundColor: 'var(--soft-cream)' }}>
          <div className="max-w-3xl mx-auto"
>

        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded mb-6">
            {error}
            <button
              onClick={() => setError(null)}
              className="float-right text-red-700 hover:text-red-900"
            >
              ×
            </button>
          </div>
        )}

        {/* Step 1: Choose action */}
        {step === 'choose' && (
          <div className="space-y-4">
            <div className="bg-white rounded-lg shadow p-6">
              <h2 className="font-semibold text-lg mb-2">Select Existing Database</h2>
              <p className="text-sm text-gray-600 mb-4">
                Choose from your existing Notion databases
              </p>
              <button
                onClick={() => setStep('select')}
                className="px-4 py-2 bg-black hover:bg-gray-800 text-white rounded-md font-medium"
              >
                Browse Databases
              </button>
            </div>

            <div className="bg-white rounded-lg shadow p-6">
              <h2 className="font-semibold text-lg mb-2">Create New Database</h2>
              <p className="text-sm text-gray-600 mb-4">
                Create a new database configured for rMirror sync
              </p>
              <button
                onClick={() => setStep('create')}
                className="px-4 py-2 bg-gray-100 hover:bg-gray-200 rounded-md font-medium"
              >
                Create Database
              </button>
            </div>

            <button
              onClick={() => router.push('/integrations')}
              className="w-full px-4 py-2 text-gray-600 hover:text-gray-800"
            >
              ← Back to Integrations
            </button>
          </div>
        )}

        {/* Step 2: Select existing database */}
        {step === 'select' && (
          <div>
            <button
              onClick={() => setStep('choose')}
              className="mb-4 text-gray-600 hover:text-gray-800"
            >
              ← Back
            </button>

            {loading ? (
              <div className="flex justify-center py-8">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-black"></div>
              </div>
            ) : databases.length === 0 ? (
              <div className="bg-white rounded-lg shadow p-6 text-center">
                <p className="text-gray-600 mb-4">No databases found</p>
                <button
                  onClick={() => setStep('create')}
                  className="px-4 py-2 bg-black hover:bg-gray-800 text-white rounded-md font-medium"
                >
                  Create New Database
                </button>
              </div>
            ) : (
              <div className="space-y-3">
                {databases.map((db) => (
                  <div
                    key={db.id}
                    className="bg-white rounded-lg shadow p-4 hover:shadow-md transition-shadow cursor-pointer"
                    onClick={() => handleSelectDatabase(db.id)}
                  >
                    <h3 className="font-semibold">{db.title}</h3>
                    <p className="text-sm text-gray-500">
                      Created: {new Date(db.created_time).toLocaleDateString()}
                    </p>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Step 3: Create new database */}
        {step === 'create' && (
          <div className="bg-white rounded-lg shadow p-6">
            <button
              onClick={() => setStep('choose')}
              className="mb-4 text-gray-600 hover:text-gray-800"
            >
              ← Back
            </button>

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium mb-2">
                  Database Title
                </label>
                <input
                  type="text"
                  value={newDbTitle}
                  onChange={(e) => setNewDbTitle(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-black"
                  placeholder="Enter database name"
                />
              </div>

              <div>
                <label className="block text-sm font-medium mb-2">
                  Parent Page (Optional)
                </label>
                <select
                  value={selectedParentPage}
                  onChange={(e) => setSelectedParentPage(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-black"
                >
                  <option value="">Create new "rMirror" page</option>
                  {pages.map((page) => (
                    <option key={page.id} value={page.id}>
                      {page.title}
                    </option>
                  ))}
                </select>
                <p className="text-sm text-gray-500 mt-1">
                  If not selected, a new "rMirror" page will be created to organize your content
                </p>
              </div>

              <button
                onClick={handleCreateDatabase}
                disabled={loading}
                className="w-full px-4 py-2 bg-black hover:bg-gray-800 text-white rounded-md font-medium disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {loading ? 'Creating...' : 'Create Database'}
              </button>
            </div>
          </div>
        )}
          </div>
        </div>
      </main>
    </div>
  );
}

export default function NotionSetupPage() {
  return (
    <Suspense
      fallback={
        <div className="flex items-center justify-center min-h-screen bg-gray-50">
          <div className="bg-white rounded-lg shadow-lg p-8">
            <div className="flex justify-center mb-4">
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-black"></div>
            </div>
            <h2 className="text-xl font-semibold text-center">Loading...</h2>
          </div>
        </div>
      }
    >
      <NotionSetupContent />
    </Suspense>
  );
}
