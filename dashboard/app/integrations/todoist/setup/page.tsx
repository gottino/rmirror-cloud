'use client';

import { Suspense, useEffect, useState } from 'react';
import { useAuth } from '@clerk/nextjs';
import UserMenu from '@/components/UserMenu';
import { useRouter } from 'next/navigation';
import { Menu } from 'lucide-react';
import Sidebar from '@/components/Sidebar';
import { getTodoistProjects, setTodoistProject, TodoistProject } from '@/lib/api';
import { trackEvent } from '@/lib/analytics';

function TodoistSetupContent() {
  const { getToken } = useAuth();
  const router = useRouter();
  const [sidebarOpen, setSidebarOpen] = useState(false);

  // Development mode bypass
  const isDevelopmentMode = process.env.NEXT_PUBLIC_DEV_MODE === 'true';

  const [projects, setProjects] = useState<TodoistProject[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string>('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadProjects();
  }, []);

  async function loadProjects() {
    setLoading(true);
    try {
      const token = isDevelopmentMode
        ? process.env.NEXT_PUBLIC_DEV_AUTH_TOKEN || localStorage.getItem('dev_auth_token') || ''
        : await getToken();
      if (!token) return;

      const data = await getTodoistProjects(token);
      setProjects(data);

      // Pre-select inbox project if available
      const inbox = data.find((p) => p.is_inbox_project);
      if (inbox) {
        setSelectedProjectId(inbox.id);
      } else if (data.length > 0) {
        setSelectedProjectId(data[0].id);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load projects');
    } finally {
      setLoading(false);
    }
  }

  async function handleSave() {
    if (!selectedProjectId) {
      setError('Please select a project');
      return;
    }

    const project = projects.find((p) => p.id === selectedProjectId);
    if (!project) return;

    setSaving(true);
    try {
      const token = isDevelopmentMode
        ? process.env.NEXT_PUBLIC_DEV_AUTH_TOKEN || localStorage.getItem('dev_auth_token') || ''
        : await getToken();
      if (!token) return;

      await setTodoistProject(token, project.id, project.name);
      trackEvent({ name: 'todoist_project_configured', data: { project_id: project.id } });
      router.push('/integrations?success=true');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save project selection');
    } finally {
      setSaving(false);
    }
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
        <header
          className="sticky top-0 z-30 border-b bg-white px-6 py-4"
          style={{ borderColor: 'var(--border)' }}
        >
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
                  Todoist Setup
                </h1>
                <p className="text-sm" style={{ color: 'var(--warm-gray)' }}>
                  Choose which Todoist project to sync your todos into
                </p>
              </div>
            </div>
            <UserMenu />
          </div>
        </header>

        {/* Content */}
        <div className="p-6" style={{ backgroundColor: 'var(--soft-cream)' }}>
          <div className="max-w-3xl mx-auto">
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
                <button
                  onClick={() => setError(null)}
                  className="float-right"
                  style={{ color: 'var(--destructive)' }}
                >
                  ×
                </button>
              </div>
            )}

            <div className="bg-white rounded-lg shadow p-6">
              <h2 className="font-semibold text-lg mb-2" style={{ color: 'var(--warm-charcoal)' }}>
                Select a Project
              </h2>
              <p className="text-sm mb-6" style={{ color: 'var(--warm-gray)' }}>
                Extracted todos from your reMarkable notebooks will be added to this project.
              </p>

              {loading ? (
                <div className="flex justify-center py-8">
                  <div
                    className="animate-spin rounded-full h-8 w-8 border-b-2"
                    style={{ borderColor: 'var(--terracotta)' }}
                  ></div>
                </div>
              ) : projects.length === 0 ? (
                <div className="text-center py-6">
                  <p className="mb-4" style={{ color: 'var(--warm-gray)' }}>
                    No projects found in your Todoist account.
                  </p>
                  <button
                    onClick={() => router.push('/integrations')}
                    className="px-4 py-2 rounded-md text-sm font-medium"
                    style={{ color: 'var(--warm-gray)' }}
                  >
                    ← Back to Integrations
                  </button>
                </div>
              ) : (
                <div className="space-y-4">
                  <div className="space-y-2">
                    {projects.map((project) => (
                      <label
                        key={project.id}
                        className="flex items-center gap-3 p-3 rounded-md cursor-pointer transition-colors"
                        style={{
                          border: `1px solid ${selectedProjectId === project.id ? 'var(--terracotta)' : 'var(--border)'}`,
                          backgroundColor:
                            selectedProjectId === project.id
                              ? 'var(--terracotta-light, #fdf3f2)'
                              : 'white',
                        }}
                      >
                        <input
                          type="radio"
                          name="project"
                          value={project.id}
                          checked={selectedProjectId === project.id}
                          onChange={() => setSelectedProjectId(project.id)}
                          className="sr-only"
                        />
                        <div
                          className="w-4 h-4 rounded-full border-2 flex items-center justify-center flex-shrink-0"
                          style={{
                            borderColor:
                              selectedProjectId === project.id
                                ? 'var(--terracotta)'
                                : 'var(--border)',
                          }}
                        >
                          {selectedProjectId === project.id && (
                            <div
                              className="w-2 h-2 rounded-full"
                              style={{ backgroundColor: 'var(--terracotta)' }}
                            />
                          )}
                        </div>
                        <div className="flex-1">
                          <span
                            className="font-medium"
                            style={{ color: 'var(--warm-charcoal)' }}
                          >
                            {project.name}
                          </span>
                          {project.is_inbox_project && (
                            <span
                              className="ml-2 text-xs px-2 py-0.5 rounded-full"
                              style={{
                                backgroundColor: 'var(--amber-gold-light)',
                                color: 'var(--amber-gold)',
                              }}
                            >
                              Inbox
                            </span>
                          )}
                        </div>
                      </label>
                    ))}
                  </div>

                  <div className="flex gap-3 pt-2">
                    <button
                      onClick={handleSave}
                      disabled={saving || !selectedProjectId}
                      className="px-6 py-2 rounded-md text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                      style={{ backgroundColor: 'var(--warm-charcoal)', color: 'white' }}
                    >
                      {saving ? 'Saving...' : 'Save Project'}
                    </button>
                    <button
                      onClick={() => router.push('/integrations')}
                      className="px-4 py-2 rounded-md text-sm font-medium transition-colors"
                      style={{ color: 'var(--warm-gray)' }}
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}

export default function TodoistSetupPage() {
  return (
    <Suspense
      fallback={
        <div
          className="flex items-center justify-center min-h-screen"
          style={{ backgroundColor: 'var(--soft-cream)' }}
        >
          <div
            className="rounded-lg shadow-lg p-8"
            style={{ backgroundColor: 'white', border: '1px solid var(--border)' }}
          >
            <div className="flex justify-center mb-4">
              <div
                className="animate-spin rounded-full h-12 w-12 border-b-2"
                style={{ borderColor: 'var(--terracotta)' }}
              ></div>
            </div>
            <h2 className="text-xl font-semibold text-center" style={{ color: 'var(--warm-charcoal)' }}>
              Loading...
            </h2>
          </div>
        </div>
      }
    >
      <TodoistSetupContent />
    </Suspense>
  );
}
