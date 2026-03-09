'use client';

import { useEffect, useState } from 'react';
import { useAuth } from '@clerk/nextjs';
import UserMenu from '@/components/UserMenu';
import { useRouter } from 'next/navigation';
import { Menu } from 'lucide-react';
import Sidebar from '@/components/Sidebar';
import {
  getIntegrations,
  getNotionOAuthUrl,
  deleteIntegration,
  testIntegrationConnection,
  IntegrationConfig,
  type IntegrationTestResult,
} from '@/lib/api';
import { trackEvent } from '@/lib/analytics';
import { timeAgo } from '@/lib/utils';

export default function IntegrationsPage() {
  const { getToken, isLoaded, isSignedIn } = useAuth();
  const router = useRouter();
  const [integrations, setIntegrations] = useState<IntegrationConfig[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [testing, setTesting] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<IntegrationTestResult | null>(null);

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
      trackEvent({ name: 'integration_setup_started', data: { service: 'notion' } });
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
      trackEvent({ name: 'integration_disconnected', data: { service: targetName } });
      await loadIntegrations();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to disconnect');
    }
  }

  async function handleTestConnection(targetName: string) {
    setTesting(targetName);
    setTestResult(null);

    try {
      const token = isDevelopmentMode
        ? process.env.NEXT_PUBLIC_DEV_AUTH_TOKEN || localStorage.getItem('dev_auth_token') || ''
        : await getToken();
      if (!token) return;

      const result = await testIntegrationConnection(token, targetName);
      setTestResult(result);
    } catch (err) {
      setTestResult({
        success: false,
        target_name: targetName,
        message: err instanceof Error ? err.message : 'Connection test failed',
      });
    } finally {
      setTesting(null);
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
            <UserMenu />
          </div>
        </header>

        {/* Content */}
        <div className="p-6" style={{ backgroundColor: 'var(--soft-cream)' }}>
          <div className="max-w-4xl mx-auto"
>

        {error && (
          <div
            className="px-4 py-3 rounded mb-6"
            style={{
              backgroundColor: 'var(--destructive-bg)',
              border: '1px solid var(--destructive-border-solid)',
              color: 'var(--destructive)',
            }}
          >
            {error}
          </div>
        )}

        {/* Notebooks Section */}
        <div className="mb-8">
          <h2 className="text-xl font-semibold mb-4">Notebooks</h2>
          <div className="bg-white rounded-lg shadow p-6">
            <div className="flex items-start gap-4">
              <div className="w-12 h-12 rounded-lg flex items-center justify-center flex-shrink-0" style={{ backgroundColor: 'var(--warm-charcoal)' }}>
                <span className="text-white font-bold">N</span>
              </div>
              <div className="flex-1">
                <h3 className="font-semibold text-lg">Notion</h3>
                {notionIntegration ? (
                  <>
                    <p className="text-sm mb-3" style={{ color: 'var(--warm-gray)' }}>
                      Status: <span style={{ color: 'var(--sage-green)', fontWeight: 500 }}>Connected</span>
                      {notionIntegration.last_synced_at && (
                        <> &middot; Last synced {timeAgo(notionIntegration.last_synced_at)}</>
                      )}
                    </p>
                    <div className="flex gap-2 flex-wrap">
                      <button
                        onClick={() => router.push('/integrations/notion/setup?type=notebooks')}
                        className="px-4 py-2 rounded-md text-sm font-medium transition-colors"
                        style={{ backgroundColor: 'var(--soft-cream)', border: '1px solid var(--border)' }}
                      >
                        Configure
                      </button>
                      <button
                        onClick={() => handleTestConnection('notion')}
                        disabled={testing === 'notion'}
                        className="px-4 py-2 rounded-md text-sm font-medium transition-colors"
                        style={{ backgroundColor: 'var(--soft-cream)', border: '1px solid var(--border)' }}
                      >
                        {testing === 'notion' ? 'Testing...' : 'Test Connection'}
                      </button>
                      <button
                        onClick={() => handleDisconnect('notion')}
                        className="px-4 py-2 rounded-md text-sm font-medium transition-colors"
                        style={{ backgroundColor: 'var(--destructive-light)', color: 'var(--destructive)' }}
                      >
                        Disconnect
                      </button>
                    </div>
                    {testResult && testResult.target_name === 'notion' && (
                      <p className="text-sm mt-2" style={{ color: testResult.success ? 'var(--sage-green)' : 'var(--destructive)' }}>
                        {testResult.message}
                      </p>
                    )}
                  </>
                ) : (
                  <>
                    <p className="text-sm mb-3" style={{ color: 'var(--warm-gray)' }}>
                      Sync your notebooks to Notion for easy access and collaboration
                    </p>
                    <button
                      onClick={handleConnectNotion}
                      className="px-4 py-2 rounded-md text-sm font-medium transition-colors"
                      style={{ backgroundColor: 'var(--warm-charcoal)', color: 'white' }}
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
              <div className="w-12 h-12 rounded-lg flex items-center justify-center flex-shrink-0" style={{ backgroundColor: 'var(--warm-charcoal)' }}>
                <span className="text-white font-bold">N</span>
              </div>
              <div className="flex-1">
                <h3 className="font-semibold text-lg">Notion Todos</h3>
                {notionTodosIntegration ? (
                  <>
                    <p className="text-sm mb-3" style={{ color: 'var(--warm-gray)' }}>
                      Status: <span style={{ color: 'var(--sage-green)', fontWeight: 500 }}>Connected</span>
                      {notionTodosIntegration.last_synced_at && (
                        <> &middot; Last synced {timeAgo(notionTodosIntegration.last_synced_at)}</>
                      )}
                    </p>
                    <div className="flex gap-2 flex-wrap">
                      <button
                        onClick={() => router.push('/integrations/notion/setup?type=todos')}
                        className="px-4 py-2 rounded-md text-sm font-medium transition-colors"
                        style={{ backgroundColor: 'var(--soft-cream)', border: '1px solid var(--border)' }}
                      >
                        Configure
                      </button>
                      <button
                        onClick={() => handleTestConnection('notion-todos')}
                        disabled={testing === 'notion-todos'}
                        className="px-4 py-2 rounded-md text-sm font-medium transition-colors"
                        style={{ backgroundColor: 'var(--soft-cream)', border: '1px solid var(--border)' }}
                      >
                        {testing === 'notion-todos' ? 'Testing...' : 'Test Connection'}
                      </button>
                      <button
                        onClick={() => handleDisconnect('notion-todos')}
                        className="px-4 py-2 rounded-md text-sm font-medium transition-colors"
                        style={{ backgroundColor: 'var(--destructive-light)', color: 'var(--destructive)' }}
                      >
                        Disconnect
                      </button>
                    </div>
                    {testResult && testResult.target_name === 'notion-todos' && (
                      <p className="text-sm mt-2" style={{ color: testResult.success ? 'var(--sage-green)' : 'var(--destructive)' }}>
                        {testResult.message}
                      </p>
                    )}
                  </>
                ) : (
                  <>
                    <p className="text-sm mb-3" style={{ color: 'var(--warm-gray)' }}>
                      Sync extracted todos to a dedicated Notion database for task management
                    </p>
                    {notionIntegration ? (
                      <button
                        onClick={() => router.push('/integrations/notion/setup?type=todos')}
                        className="px-4 py-2 rounded-md text-sm font-medium transition-colors"
                        style={{ backgroundColor: 'var(--warm-charcoal)', color: 'white' }}
                      >
                        Connect Notion Todos
                      </button>
                    ) : (
                      <p className="text-sm italic" style={{ color: 'var(--warm-gray)' }}>
                        Connect Notion for notebooks first to enable todo sync
                      </p>
                    )}
                  </>
                )}
              </div>
            </div>
          </div>

          {/* Todoist (Coming Soon) */}
          <div
            className="rounded-lg p-6 mb-4"
            style={{ backgroundColor: 'var(--soft-cream)', border: '1px dashed var(--border)' }}
          >
            <div className="flex items-start gap-4">
              <div className="w-12 h-12 rounded-lg flex items-center justify-center flex-shrink-0" style={{ backgroundColor: 'var(--terracotta)' }}>
                <span className="text-white font-bold">T</span>
              </div>
              <div className="flex-1">
                <h3 className="font-semibold text-lg">Todoist</h3>
                <p className="text-sm mb-3" style={{ color: 'var(--warm-gray)' }}>
                  Sync todos to Todoist for powerful task management
                </p>
                <span
                  className="inline-block px-3 py-1 rounded-full text-xs font-medium"
                  style={{ backgroundColor: 'var(--amber-gold-light)', color: 'var(--amber-gold)' }}
                >
                  Coming Soon
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* Highlights Section (Coming Soon) */}
        <div className="mb-8">
          <h2 className="text-xl font-semibold mb-4">Highlights</h2>
          <div
            className="rounded-lg p-6"
            style={{ backgroundColor: 'var(--soft-cream)', border: '1px dashed var(--border)' }}
          >
            <div className="flex items-start gap-4">
              <div className="w-12 h-12 rounded-lg flex items-center justify-center flex-shrink-0" style={{ backgroundColor: 'var(--amber-gold)' }}>
                <span className="text-white font-bold">R</span>
              </div>
              <div className="flex-1">
                <h3 className="font-semibold text-lg">Readwise</h3>
                <p className="text-sm mb-3" style={{ color: 'var(--warm-gray)' }}>
                  Sync highlights to Readwise for spaced repetition
                </p>
                <span
                  className="inline-block px-3 py-1 rounded-full text-xs font-medium"
                  style={{ backgroundColor: 'var(--amber-gold-light)', color: 'var(--amber-gold)' }}
                >
                  Coming Soon
                </span>
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
