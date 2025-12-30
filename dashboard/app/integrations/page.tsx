'use client';

import { useEffect, useState } from 'react';
import { useAuth, UserButton } from '@clerk/nextjs';
import { useRouter } from 'next/navigation';
import { Menu } from 'lucide-react';
import Sidebar from '@/components/Sidebar';
import {
  getIntegrations,
  getNotionOAuthUrl,
  deleteIntegration,
  IntegrationConfig,
} from '@/lib/api';

export default function IntegrationsPage() {
  const { getToken, isLoaded, isSignedIn } = useAuth();
  const router = useRouter();
  const [integrations, setIntegrations] = useState<IntegrationConfig[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);

  // Development mode bypass
  const isDevelopmentMode = process.env.NEXT_PUBLIC_DEV_MODE === 'true';
  const effectiveIsSignedIn = isDevelopmentMode || isSignedIn;

  useEffect(() => {
    if (isDevelopmentMode || isLoaded) {
      loadIntegrations();
    }
  }, [isLoaded, isDevelopmentMode]);

  async function loadIntegrations() {
    try {
      const token = isDevelopmentMode
        ? process.env.NEXT_PUBLIC_DEV_AUTH_TOKEN || localStorage.getItem('dev_auth_token') || ''
        : await getToken();
      console.log('Got token:', token ? 'yes' : 'no');
      if (!token) {
        setError('No authentication token available');
        return;
      }

      console.log('Fetching integrations...');
      const data = await getIntegrations(token);
      console.log('Integrations loaded:', data);
      setIntegrations(data);
    } catch (err) {
      console.error('Failed to load integrations:', err);
      setError(err instanceof Error ? err.message : 'Failed to load integrations');
    } finally {
      setLoading(false);
    }
  }

  async function handleConnectNotion() {
    try {
      setLoading(true);
      const token = isDevelopmentMode
        ? process.env.NEXT_PUBLIC_DEV_AUTH_TOKEN || localStorage.getItem('dev_auth_token') || ''
        : await getToken();
      if (!token) {
        setError('Not authenticated');
        return;
      }

      console.log('Getting Notion OAuth URL...');
      const { authorization_url } = await getNotionOAuthUrl(token);
      console.log('Redirecting to:', authorization_url);
      window.location.href = authorization_url;
    } catch (err) {
      console.error('OAuth error:', err);
      setError(err instanceof Error ? err.message : 'Failed to start OAuth');
      setLoading(false);
    }
  }

  async function handleDisconnect(targetName: string) {
    if (!confirm(`Are you sure you want to disconnect ${targetName}?`)) {
      return;
    }

    try {
      const token = isDevelopmentMode
        ? process.env.NEXT_PUBLIC_DEV_AUTH_TOKEN || localStorage.getItem('dev_auth_token') || ''
        : await getToken();
      if (!token) return;

      await deleteIntegration(token, targetName);
      await loadIntegrations();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to disconnect');
    }
  }

  const notionIntegration = integrations.find((i) => i.target_name === 'notion');
  const notionTodosIntegration = integrations.find((i) => i.target_name === 'notion-todos');

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-lg">Loading integrations...</div>
      </div>
    );
  }

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
                  Integrations
                </h1>
                <p className="text-sm" style={{ color: 'var(--warm-gray)' }}>
                  Connect your rMirror notebooks and todos to external services
                </p>
              </div>
            </div>
            <UserButton />
          </div>
        </header>

        {/* Content */}
        <div className="p-6" style={{ backgroundColor: 'var(--soft-cream)' }}>
          <div className="max-w-4xl mx-auto"
>

        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded mb-6">
            {error}
          </div>
        )}

        {/* Notebooks Section */}
        <div className="mb-8">
          <h2 className="text-xl font-semibold mb-4">Notebooks</h2>
          <div className="bg-white rounded-lg shadow p-6">
            <div className="flex items-start gap-4">
              <div className="w-12 h-12 bg-black rounded-lg flex items-center justify-center flex-shrink-0">
                <span className="text-white font-bold">N</span>
              </div>
              <div className="flex-1">
                <h3 className="font-semibold text-lg">Notion</h3>
                {notionIntegration ? (
                  <>
                    <p className="text-sm text-gray-600 mb-3">
                      Status: <span className="text-green-600 font-medium">Connected</span>
                    </p>
                    <div className="flex gap-2">
                      <button
                        onClick={() => router.push('/integrations/notion/setup?type=notebooks')}
                        className="px-4 py-2 bg-gray-100 hover:bg-gray-200 rounded-md text-sm font-medium"
                      >
                        Configure
                      </button>
                      <button
                        onClick={() => handleDisconnect('notion')}
                        className="px-4 py-2 bg-red-50 hover:bg-red-100 text-red-600 rounded-md text-sm font-medium"
                      >
                        Disconnect
                      </button>
                    </div>
                  </>
                ) : (
                  <>
                    <p className="text-sm text-gray-600 mb-3">
                      Sync your notebooks to Notion for easy access and collaboration
                    </p>
                    <button
                      onClick={handleConnectNotion}
                      className="px-4 py-2 bg-black hover:bg-gray-800 text-white rounded-md text-sm font-medium"
                    >
                      Connect Notion
                    </button>
                  </>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* Todos Section */}
        <div className="mb-8">
          <h2 className="text-xl font-semibold mb-4">Todos</h2>

          {/* Notion Todos */}
          <div className="bg-white rounded-lg shadow p-6 mb-4">
            <div className="flex items-start gap-4">
              <div className="w-12 h-12 bg-black rounded-lg flex items-center justify-center flex-shrink-0">
                <span className="text-white font-bold">N</span>
              </div>
              <div className="flex-1">
                <h3 className="font-semibold text-lg">Notion Todos</h3>
                {notionTodosIntegration ? (
                  <>
                    <p className="text-sm text-gray-600 mb-3">
                      Status: <span className="text-green-600 font-medium">Connected</span>
                    </p>
                    <div className="flex gap-2">
                      <button
                        onClick={() => router.push('/integrations/notion/setup?type=todos')}
                        className="px-4 py-2 bg-gray-100 hover:bg-gray-200 rounded-md text-sm font-medium"
                      >
                        Configure
                      </button>
                      <button
                        onClick={() => handleDisconnect('notion-todos')}
                        className="px-4 py-2 bg-red-50 hover:bg-red-100 text-red-600 rounded-md text-sm font-medium"
                      >
                        Disconnect
                      </button>
                    </div>
                  </>
                ) : (
                  <>
                    <p className="text-sm text-gray-600 mb-3">
                      Sync extracted todos to a dedicated Notion database for task management
                    </p>
                    {notionIntegration ? (
                      <button
                        onClick={() => router.push('/integrations/notion/setup?type=todos')}
                        className="px-4 py-2 bg-black hover:bg-gray-800 text-white rounded-md text-sm font-medium"
                      >
                        Connect Notion Todos
                      </button>
                    ) : (
                      <p className="text-sm text-gray-500 italic">
                        Connect Notion for notebooks first to enable todo sync
                      </p>
                    )}
                  </>
                )}
              </div>
            </div>
          </div>

          {/* Todoist (Coming Soon) */}
          <div className="bg-white rounded-lg shadow p-6 mb-4 opacity-60">
            <div className="flex items-start gap-4">
              <div className="w-12 h-12 bg-red-500 rounded-lg flex items-center justify-center flex-shrink-0">
                <span className="text-white font-bold">T</span>
              </div>
              <div className="flex-1">
                <h3 className="font-semibold text-lg">Todoist</h3>
                <p className="text-sm text-gray-600 mb-3">
                  Coming soon - Sync todos to Todoist for powerful task management
                </p>
                <button
                  disabled
                  className="px-4 py-2 bg-gray-200 text-gray-400 rounded-md text-sm font-medium cursor-not-allowed"
                >
                  Coming Soon
                </button>
              </div>
            </div>
          </div>
        </div>

        {/* Highlights Section (Coming Soon) */}
        <div className="mb-8">
          <h2 className="text-xl font-semibold mb-4">Highlights (Coming Soon)</h2>
          <div className="bg-white rounded-lg shadow p-6 opacity-60">
            <div className="flex items-start gap-4">
              <div className="w-12 h-12 bg-yellow-500 rounded-lg flex items-center justify-center flex-shrink-0">
                <span className="text-white font-bold">R</span>
              </div>
              <div className="flex-1">
                <h3 className="font-semibold text-lg">Readwise</h3>
                <p className="text-sm text-gray-600 mb-3">
                  Coming soon - Sync highlights to Readwise for spaced repetition
                </p>
                <button
                  disabled
                  className="px-4 py-2 bg-gray-200 text-gray-400 rounded-md text-sm font-medium cursor-not-allowed"
                >
                  Coming Soon
                </button>
              </div>
            </div>
          </div>
        </div>
          </div>
        </div>
      </main>
    </div>
  );
}
