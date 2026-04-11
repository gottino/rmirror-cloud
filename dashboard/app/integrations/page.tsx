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
  enableObsidian,
  regenerateObsidianKey,
  disableObsidian,
  getObsidianStatus,
  type ObsidianStatusResponse,
  getTodoistOAuthUrl,
  getTodoistStatus,
  disconnectTodoist,
  type TodoistStatus,
} from '@/lib/api';
import { Copy, Check } from 'lucide-react';
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
  const [obsidianStatus, setObsidianStatus] = useState<ObsidianStatusResponse | null>(null);
  const [obsidianApiKey, setObsidianApiKey] = useState<string | null>(null);
  const [obsidianCopied, setObsidianCopied] = useState(false);
  const [obsidianLoading, setObsidianLoading] = useState(false);
  const [todoistStatus, setTodoistStatus] = useState<TodoistStatus | null>(null);
  const [todoistLoading, setTodoistLoading] = useState(false);

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

      // Also load Obsidian status
      try {
        const obsStatus = await getObsidianStatus(token);
        setObsidianStatus(obsStatus);
      } catch {
        // Obsidian not enabled yet, ignore
      }

      // Also load Todoist status
      try {
        const tdStatus = await getTodoistStatus(token);
        setTodoistStatus(tdStatus);
      } catch {
        // Todoist not connected yet
      }
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

  async function handleEnableObsidian() {
    setObsidianLoading(true);
    try {
      const token = isDevelopmentMode
        ? process.env.NEXT_PUBLIC_DEV_AUTH_TOKEN || localStorage.getItem('dev_auth_token') || ''
        : await getToken();
      if (!token) return;

      const result = await enableObsidian(token);
      setObsidianApiKey(result.api_key);
      setObsidianStatus({ enabled: true, last_sync: null, total_notebooks_synced: 0, total_pages_synced: 0, pending_notebooks: 0 });
      trackEvent({ name: 'integration_setup_started', data: { service: 'obsidian' } });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to enable Obsidian');
    } finally {
      setObsidianLoading(false);
    }
  }

  async function handleRegenerateObsidianKey() {
    if (!confirm('This will invalidate your current API key. Any connected Obsidian plugin will need the new key. Continue?')) return;
    setObsidianLoading(true);
    try {
      const token = isDevelopmentMode
        ? process.env.NEXT_PUBLIC_DEV_AUTH_TOKEN || localStorage.getItem('dev_auth_token') || ''
        : await getToken();
      if (!token) return;

      const result = await regenerateObsidianKey(token);
      setObsidianApiKey(result.api_key);
      setObsidianCopied(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to regenerate key');
    } finally {
      setObsidianLoading(false);
    }
  }

  async function handleDisableObsidian() {
    if (!confirm('Are you sure you want to disconnect Obsidian? Your synced files will remain in your vault.')) return;
    try {
      const token = isDevelopmentMode
        ? process.env.NEXT_PUBLIC_DEV_AUTH_TOKEN || localStorage.getItem('dev_auth_token') || ''
        : await getToken();
      if (!token) return;

      await disableObsidian(token);
      setObsidianStatus(null);
      setObsidianApiKey(null);
      trackEvent({ name: 'integration_disconnected', data: { service: 'obsidian' } });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to disable Obsidian');
    }
  }

  function handleCopyApiKey() {
    if (obsidianApiKey) {
      navigator.clipboard.writeText(obsidianApiKey);
      setObsidianCopied(true);
      setTimeout(() => setObsidianCopied(false), 2000);
    }
  }

  async function handleConnectTodoist() {
    try {
      setTodoistLoading(true);
      const token = isDevelopmentMode
        ? process.env.NEXT_PUBLIC_DEV_AUTH_TOKEN || localStorage.getItem('dev_auth_token') || ''
        : await getToken();
      if (!token) { setError('Not authenticated'); return; }
      const { authorization_url } = await getTodoistOAuthUrl(token);
      trackEvent({ name: 'integration_setup_started', data: { service: 'todoist' } });
      window.location.href = authorization_url;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start OAuth');
      setTodoistLoading(false);
    }
  }

  async function handleDisconnectTodoist() {
    if (!confirm('Are you sure you want to disconnect Todoist?')) return;
    try {
      setTodoistLoading(true);
      const token = isDevelopmentMode
        ? process.env.NEXT_PUBLIC_DEV_AUTH_TOKEN || localStorage.getItem('dev_auth_token') || ''
        : await getToken();
      if (!token) { setError('Not authenticated'); return; }
      await disconnectTodoist(token);
      setTodoistStatus(null);
      trackEvent({ name: 'integration_disconnected', data: { service: 'todoist' } });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to disconnect Todoist');
    } finally {
      setTodoistLoading(false);
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

        {/* Knowledge Base Section */}
        <div className="mb-8">
          <h2 className="text-xl font-semibold mb-4">Knowledge Base</h2>
          <div className="bg-white rounded-lg shadow p-6">
            <div className="flex items-start gap-4">
              <div className="w-12 h-12 rounded-lg flex items-center justify-center flex-shrink-0" style={{ backgroundColor: '#7c3aed' }}>
                <span className="text-white font-bold">O</span>
              </div>
              <div className="flex-1">
                <h3 className="font-semibold text-lg">Obsidian</h3>
                {obsidianStatus?.enabled && obsidianApiKey ? (
                  <>
                    <p className="text-sm mb-3" style={{ color: 'var(--warm-gray)' }}>
                      Copy your API key and paste it into the rMirror Obsidian plugin settings.
                    </p>
                    <div className="flex items-center gap-2 mb-3">
                      <code
                        className="flex-1 px-3 py-2 rounded text-sm font-mono break-all"
                        style={{ backgroundColor: 'var(--soft-cream)', border: '1px solid var(--border)' }}
                      >
                        {obsidianApiKey}
                      </code>
                      <button
                        onClick={handleCopyApiKey}
                        className="p-2 rounded-md transition-colors flex-shrink-0"
                        style={{ backgroundColor: 'var(--soft-cream)', border: '1px solid var(--border)' }}
                        title="Copy API key"
                      >
                        {obsidianCopied ? <Check className="w-4 h-4" style={{ color: 'var(--sage-green)' }} /> : <Copy className="w-4 h-4" />}
                      </button>
                    </div>
                    <button
                      onClick={() => { setObsidianApiKey(null); }}
                      className="px-4 py-2 rounded-md text-sm font-medium transition-colors"
                      style={{ backgroundColor: 'var(--warm-charcoal)', color: 'white' }}
                    >
                      Done
                    </button>
                  </>
                ) : obsidianStatus?.enabled ? (
                  <>
                    <p className="text-sm mb-3" style={{ color: 'var(--warm-gray)' }}>
                      Status: <span style={{ color: 'var(--sage-green)', fontWeight: 500 }}>Connected</span>
                      {obsidianStatus.last_sync && (
                        <> &middot; Last synced {timeAgo(obsidianStatus.last_sync)}</>
                      )}
                      {obsidianStatus.total_notebooks_synced > 0 && (
                        <> &middot; {obsidianStatus.total_notebooks_synced} notebook{obsidianStatus.total_notebooks_synced !== 1 ? 's' : ''} synced</>
                      )}
                      {obsidianStatus.pending_notebooks > 0 && (
                        <> &middot; {obsidianStatus.pending_notebooks} pending</>
                      )}
                    </p>
                    <div className="flex gap-2 flex-wrap">
                      <button
                        onClick={handleRegenerateObsidianKey}
                        disabled={obsidianLoading}
                        className="px-4 py-2 rounded-md text-sm font-medium transition-colors"
                        style={{ backgroundColor: 'var(--soft-cream)', border: '1px solid var(--border)' }}
                      >
                        {obsidianLoading ? 'Regenerating...' : 'Regenerate Key'}
                      </button>
                      <button
                        onClick={handleDisableObsidian}
                        className="px-4 py-2 rounded-md text-sm font-medium transition-colors"
                        style={{ backgroundColor: 'var(--destructive-light)', color: 'var(--destructive)' }}
                      >
                        Disconnect
                      </button>
                    </div>
                  </>
                ) : (
                  <>
                    <p className="text-sm mb-3" style={{ color: 'var(--warm-gray)' }}>
                      Sync your notebooks to Obsidian as Markdown files for local-first knowledge management
                    </p>
                    <button
                      onClick={handleEnableObsidian}
                      disabled={obsidianLoading}
                      className="px-4 py-2 rounded-md text-sm font-medium transition-colors"
                      style={{ backgroundColor: 'var(--warm-charcoal)', color: 'white' }}
                    >
                      {obsidianLoading ? 'Connecting...' : 'Connect Obsidian'}
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

          {/* Todoist */}
          <div className="bg-white rounded-lg shadow p-6 mb-4">
            <div className="flex items-start gap-4">
              <div className="w-12 h-12 rounded-lg flex items-center justify-center flex-shrink-0" style={{ backgroundColor: 'var(--terracotta)' }}>
                <span className="text-white font-bold">T</span>
              </div>
              <div className="flex-1">
                <h3 className="font-semibold text-lg">Todoist</h3>
                {todoistStatus?.connected ? (
                  <>
                    <p className="text-sm mb-3" style={{ color: 'var(--warm-gray)' }}>
                      Status: <span style={{ color: 'var(--sage-green)', fontWeight: 500 }}>Connected</span>
                      {todoistStatus.project_name && (
                        <> &middot; Project: <strong>{todoistStatus.project_name}</strong></>
                      )}
                      {todoistStatus.todos_synced > 0 && (
                        <> &middot; {todoistStatus.todos_synced} todo{todoistStatus.todos_synced !== 1 ? 's' : ''} synced</>
                      )}
                      {todoistStatus.last_sync && (
                        <> &middot; Last synced {timeAgo(todoistStatus.last_sync)}</>
                      )}
                    </p>
                    <div className="flex gap-2 flex-wrap">
                      <button
                        onClick={() => router.push('/integrations/todoist/setup')}
                        className="px-4 py-2 rounded-md text-sm font-medium transition-colors"
                        style={{ backgroundColor: 'var(--soft-cream)', border: '1px solid var(--border)' }}
                      >
                        Change Project
                      </button>
                      <button
                        onClick={handleDisconnectTodoist}
                        disabled={todoistLoading}
                        className="px-4 py-2 rounded-md text-sm font-medium transition-colors"
                        style={{ backgroundColor: 'var(--destructive-light)', color: 'var(--destructive)' }}
                      >
                        {todoistLoading ? 'Disconnecting...' : 'Disconnect'}
                      </button>
                    </div>
                  </>
                ) : (
                  <>
                    <p className="text-sm mb-3" style={{ color: 'var(--warm-gray)' }}>
                      Sync todos to Todoist for powerful task management
                    </p>
                    <button
                      onClick={handleConnectTodoist}
                      disabled={todoistLoading}
                      className="px-4 py-2 rounded-md text-sm font-medium transition-colors"
                      style={{ backgroundColor: 'var(--warm-charcoal)', color: 'white' }}
                    >
                      {todoistLoading ? 'Connecting...' : 'Connect Todoist'}
                    </button>
                  </>
                )}
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
